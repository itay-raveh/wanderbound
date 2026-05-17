from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import get_settings
from app.logic.upload import TripMeta

from .factories import (
    GOOGLE_PAYLOAD,
    MICROSOFT_PAYLOAD,
    PS_USER,
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
            resp = await user_routes.auth(provider)
        assert resp.status_code == 200
        assert resp.json() is None

    async def test_existing_user_returns_user(
        self,
        user_routes: UserRoutes,
        users_dir: Path,
        provider: str,
        sub_field: str,
        sub_value: str,
    ) -> None:
        await user_routes.sign_in_and_upload(users_dir, provider=provider)
        await user_routes.logout()

        with mock_jwt(provider):
            resp = await user_routes.auth(provider)
        assert resp.status_code == 200
        user = resp.json()
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
        user = await user_routes.sign_in_and_upload(
            users_dir, provider="microsoft", payload=no_given
        )
        assert user["first_name"] == "Test Microsoft"


class TestLogout:
    @pytest.mark.usefixtures("uploaded_user")
    async def test_clears_session(self, user_routes: UserRoutes) -> None:
        await user_routes.logout()
        resp = await user_routes.current()
        assert resp.status_code == 401


class TestUpload:
    async def test_no_session(self, user_routes: UserRoutes) -> None:
        resp = await user_routes.upload()
        assert resp.status_code == 401

    async def test_new_user_google(self, uploaded_user: dict) -> None:
        assert uploaded_user["google_sub"] == "google-123"
        assert uploaded_user["microsoft_sub"] is None
        assert uploaded_user["first_name"] == "Test"  # Google name preferred over ZIP

    async def test_new_user_microsoft(
        self, user_routes: UserRoutes, users_dir: Path
    ) -> None:
        user = await user_routes.sign_in_and_upload(users_dir, provider="microsoft")
        assert user["microsoft_sub"] == "microsoft-456"
        assert user["google_sub"] is None
        assert user["first_name"] == "Test"  # from given_name in token

    async def test_falls_back_to_zip_name(
        self, user_routes: UserRoutes, users_dir: Path
    ) -> None:
        no_name = {**GOOGLE_PAYLOAD, "given_name": "", "family_name": ""}
        await user_routes.sign_in(payload=no_name)
        resp = await user_routes.upload_with_extract(users_dir)
        user = resp.json()["user"]
        assert user["first_name"] == "Zip"

    @pytest.mark.usefixtures("uploaded_user")
    async def test_reupload_updates_trips(
        self, user_routes: UserRoutes, users_dir: Path
    ) -> None:
        new_trips = [
            TripMeta(id="trip-2", title="New Trip", step_count=3, country_codes=["de"])
        ]
        folder = Path(tempfile.mkdtemp(dir=users_dir))
        with patch(
            "app.api.v1.routes.users.extract_and_scan",
            return_value=(folder, PS_USER, new_trips),
        ):
            resp = await user_routes.upload()
        assert resp.status_code == 200
        assert resp.json()["trips"][0]["id"] == "trip-2"


class TestUpdateUser:
    @pytest.mark.usefixtures("uploaded_user")
    async def test_update_locale(self, user_routes: UserRoutes) -> None:
        resp = await user_routes.update(locale="he-IL")
        assert resp.status_code == 200
        assert resp.json()["locale"] == "he-IL"


class TestDeleteUser:
    @pytest.mark.usefixtures("uploaded_user")
    async def test_clears_session(self, user_routes: UserRoutes) -> None:
        resp = await user_routes.delete()
        assert resp.status_code == 200
        resp = await user_routes.current()
        assert resp.status_code == 401

    async def test_removes_folder(
        self, user_routes: UserRoutes, users_dir: Path, uploaded_user: dict
    ) -> None:
        user_folder = users_dir / str(uploaded_user["id"])
        assert user_folder.exists()
        await user_routes.delete()
        assert not user_folder.exists()
