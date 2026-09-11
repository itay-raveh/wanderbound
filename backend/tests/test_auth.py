from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.core.config import get_settings
from app.models.album import Album
from app.models.user import User

from .factories import (
    MICROSOFT_PAYLOAD,
    PS_USER,
    mock_jwt,
)
from .helpers.users import UserRoutes

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession


class TestLocalLogin:
    @pytest.fixture
    async def local_user(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> User:
        monkeypatch.setattr(get_settings(), "GOOGLE_CLIENT_ID", "")
        monkeypatch.setattr(get_settings(), "MICROSOFT_CLIENT_ID", "")
        user = User(**PS_USER.model_dump(), album_ids=["trip-1"])
        session.add(user)
        await session.commit()
        return user

    async def test_resumes_saved_album(
        self, client: AsyncClient, session: AsyncSession, local_user: User
    ) -> None:
        trip = local_user.trips_folder / "trip-1"
        trip.mkdir(parents=True)
        saved_file = trip / "saved.txt"
        saved_file.write_text("saved album content")
        album = Album(uid=local_user.id, id="trip-1", colors={}, hidden_steps=[42])
        session.add(album)
        await session.commit()

        listed = await client.get("/api/v1/auth/local")
        assert listed.json() == [
            {"id": local_user.id, "first_name": local_user.first_name}
        ]
        result = await client.post(f"/api/v1/auth/local/{local_user.id}")
        assert result.status_code == 200
        assert result.json()["is_processed"] is True
        current = await client.get("/api/v1/users")
        assert current.json()["id"] == local_user.id
        await session.refresh(album)
        assert album.hidden_steps == [42]
        assert saved_file.read_text() == "saved album content"

    @pytest.mark.parametrize(
        "kind", ["google_sub", "microsoft_sub", "is_demo", "missing"]
    )
    async def test_rejects_non_local_accounts(
        self, client: AsyncClient, session: AsyncSession, local_user: User, kind: str
    ) -> None:
        if kind != "missing":
            setattr(local_user, kind, True if kind == "is_demo" else "external-user")
            session.add(local_user)
            await session.commit()
            assert (await client.get("/api/v1/auth/local")).json() == []
        uid = -1 if kind == "missing" else local_user.id
        assert (await client.post(f"/api/v1/auth/local/{uid}")).status_code == 404
        assert (await client.get("/api/v1/users")).status_code == 401

    @pytest.mark.parametrize("provider", ["GOOGLE_CLIENT_ID", "MICROSOFT_CLIENT_ID"])
    async def test_disabled_with_oauth(
        self,
        client: AsyncClient,
        local_user: User,
        monkeypatch: pytest.MonkeyPatch,
        provider: str,
    ) -> None:
        monkeypatch.setattr(get_settings(), provider, "configured")
        assert (await client.get("/api/v1/auth/local")).status_code == 404
        assert (
            await client.post(f"/api/v1/auth/local/{local_user.id}")
        ).status_code == 404
        assert (await client.get("/api/v1/users")).status_code == 401


@pytest.mark.parametrize(
    ("provider", "sub_field", "sub_value"),
    [
        ("google", "google_sub", "google-123"),
        ("microsoft", "microsoft_sub", "microsoft-456"),
    ],
)
class TestAuthProvider:
    async def test_invalid_jwt(
        self,
        user_routes: UserRoutes,
        provider: str,
        sub_field: str,
        sub_value: str,
    ) -> None:
        _ = sub_field, sub_value
        with mock_jwt(provider, decode_error=True):
            resp = await user_routes.auth(provider, "bad")
        assert resp.status_code == 401

    async def test_new_user_returns_null(
        self,
        user_routes: UserRoutes,
        provider: str,
        sub_field: str,
        sub_value: str,
    ) -> None:
        _ = sub_field, sub_value
        with mock_jwt(provider):
            assert await user_routes.auth_ok(provider) is None

    async def test_existing_user_returns_user(
        self,
        user_routes: UserRoutes,
        users_dir: Path,
        provider: str,
        sub_field: str,
        sub_value: str,
    ) -> None:
        await user_routes.sign_in_user(users_dir, provider=provider)
        await user_routes.logout()

        with mock_jwt(provider):
            user = await user_routes.auth_ok(provider)
        assert user is not None
        assert user[sub_field] == sub_value


class TestAuthMicrosoftSpecific:
    @pytest.mark.parametrize("issuer", ["https://evil.example.com/v2.0", None, 42])
    async def test_bad_issuer_returns_401(
        self, user_routes: UserRoutes, issuer: object
    ) -> None:
        bad_iss = {**MICROSOFT_PAYLOAD, "iss": issuer}
        with mock_jwt("microsoft", payload=bad_iss):
            resp = await user_routes.auth("microsoft")
        assert resp.status_code == 401

    async def test_not_configured_returns_501(
        self, user_routes: UserRoutes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "MICROSOFT_CLIENT_ID", "")
        with mock_jwt("microsoft", ensure_configured=False):
            resp = await user_routes.auth("microsoft")
        assert resp.status_code == 501

    async def test_falls_back_to_name_when_no_given_name(
        self, user_routes: UserRoutes, users_dir: Path
    ) -> None:
        no_given = {k: v for k, v in MICROSOFT_PAYLOAD.items() if k != "given_name"}
        user = await user_routes.sign_in_user(
            users_dir, provider="microsoft", payload=no_given
        )
        assert user["first_name"] == "Test Microsoft"


class TestLogout:
    @pytest.mark.usefixtures("uploaded_user")
    async def test_clears_session(self, user_routes: UserRoutes) -> None:
        await user_routes.logout()
        resp = await user_routes.current()
        assert resp.status_code == 401


class TestDeleteUser:
    @pytest.mark.usefixtures("uploaded_user")
    async def test_clears_session(self, user_routes: UserRoutes) -> None:
        await user_routes.delete_ok()
        resp = await user_routes.current()
        assert resp.status_code == 401

    async def test_removes_folder(
        self, user_routes: UserRoutes, users_dir: Path, uploaded_user: dict
    ) -> None:
        user_folder = users_dir / str(uploaded_user["id"])
        assert user_folder.exists()
        await user_routes.delete_ok()
        assert not user_folder.exists()
