from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import get_settings

from .factories import (
    MICROSOFT_PAYLOAD,
    mock_jwt,
)
from .helpers.users import UserRoutes


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
    async def test_bad_issuer_returns_401(self, user_routes: UserRoutes) -> None:
        bad_iss = {**MICROSOFT_PAYLOAD, "iss": "https://evil.example.com/v2.0"}
        with mock_jwt("microsoft", payload=bad_iss):
            resp = await user_routes.auth("microsoft")
        assert resp.status_code == 401

    async def test_not_configured_returns_501(
        self, user_routes: UserRoutes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "VITE_MICROSOFT_CLIENT_ID", "")
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


class TestUpdateUser:
    @pytest.mark.usefixtures("uploaded_user")
    async def test_update_locale(self, user_routes: UserRoutes) -> None:
        resp = await user_routes.update(locale="he-IL")
        assert resp.status_code == 200
        assert resp.json()["locale"] == "he-IL"


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
