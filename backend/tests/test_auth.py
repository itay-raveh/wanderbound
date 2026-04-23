from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from app.core.config import get_settings
from app.logic.upload import TripMeta

from .factories import (
    GOOGLE_PAYLOAD,
    MICROSOFT_PAYLOAD,
    PS_USER,
    mock_extract,
    mock_jwt,
    sign_in_and_upload,
)

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.parametrize(
    ("provider", "sub_field", "sub_value"),
    [
        ("google", "google_sub", "google-123"),
        ("microsoft", "microsoft_sub", "microsoft-456"),
    ],
)
class TestAuthProvider:
    async def test_invalid_jwt(
        self, client: AsyncClient, provider: str, sub_field: str, sub_value: str
    ) -> None:
        _ = sub_field, sub_value
        with mock_jwt(provider, decode_error=True):
            resp = await client.post(
                f"/api/v1/auth/{provider}", json={"credential": "bad"}
            )
        assert resp.status_code == 401

    async def test_new_user_returns_null(
        self, client: AsyncClient, provider: str, sub_field: str, sub_value: str
    ) -> None:
        _ = sub_field, sub_value
        with mock_jwt(provider):
            resp = await client.post(
                f"/api/v1/auth/{provider}", json={"credential": "fake"}
            )
        assert resp.status_code == 200
        assert resp.json() is None

    async def test_existing_user_returns_user(
        self,
        client: AsyncClient,
        tmp_path: Path,
        provider: str,
        sub_field: str,
        sub_value: str,
    ) -> None:
        await sign_in_and_upload(client, tmp_path / "users", provider=provider)
        await client.post("/api/v1/auth/logout")

        with mock_jwt(provider):
            resp = await client.post(
                f"/api/v1/auth/{provider}", json={"credential": "fake"}
            )
        assert resp.status_code == 200
        user = resp.json()
        assert user is not None
        assert user[sub_field] == sub_value


class TestAuthMicrosoftSpecific:
    """Tests specific to Microsoft auth."""

    async def test_bad_issuer_returns_401(self, client: AsyncClient) -> None:
        bad_iss = {**MICROSOFT_PAYLOAD, "iss": "https://evil.example.com/v2.0"}
        with mock_jwt("microsoft", payload=bad_iss):
            resp = await client.post(
                "/api/v1/auth/microsoft", json={"credential": "fake"}
            )
        assert resp.status_code == 401

    async def test_not_configured_returns_501(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "VITE_MICROSOFT_CLIENT_ID", "")
        with mock_jwt("microsoft", ensure_configured=False):
            resp = await client.post(
                "/api/v1/auth/microsoft", json={"credential": "fake"}
            )
        assert resp.status_code == 501

    async def test_falls_back_to_name_when_no_given_name(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        no_given = {k: v for k, v in MICROSOFT_PAYLOAD.items() if k != "given_name"}
        user = await sign_in_and_upload(
            client, tmp_path / "users", provider="microsoft", payload=no_given
        )
        assert user["first_name"] == "Test Microsoft"


class TestLogout:
    async def test_clears_session(self, client: AsyncClient, tmp_path: Path) -> None:
        await sign_in_and_upload(client, tmp_path / "users")
        await client.post("/api/v1/auth/logout")
        resp = await client.get("/api/v1/users")
        assert resp.status_code == 401


class TestUpload:
    async def test_no_session(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/users/upload",
            files={"file": ("data.zip", b"fake", "application/zip")},
        )
        assert resp.status_code == 401

    async def test_new_user_google(self, client: AsyncClient, tmp_path: Path) -> None:
        user = await sign_in_and_upload(client, tmp_path / "users")
        assert user["google_sub"] == "google-123"
        assert user["microsoft_sub"] is None
        assert user["first_name"] == "Test"  # Google name preferred over ZIP

    async def test_new_user_microsoft(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        user = await sign_in_and_upload(
            client, tmp_path / "users", provider="microsoft"
        )
        assert user["microsoft_sub"] == "microsoft-456"
        assert user["google_sub"] is None
        assert user["first_name"] == "Test"  # from given_name in token

    async def test_falls_back_to_zip_name(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        no_name = {**GOOGLE_PAYLOAD, "given_name": "", "family_name": ""}
        with mock_jwt(payload=no_name):
            auth_resp = await client.post(
                "/api/v1/auth/google", json={"credential": "fake"}
            )
        assert auth_resp.status_code == 200
        with mock_extract(tmp_path / "users"):
            resp = await client.post(
                "/api/v1/users/upload",
                files={"file": ("data.zip", b"fake", "application/zip")},
            )
        user = resp.json()["user"]
        assert user["first_name"] == "Zip"

    async def test_reupload_updates_trips(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        await sign_in_and_upload(client, tmp_path / "users")

        new_trips = [
            TripMeta(id="trip-2", title="New Trip", step_count=3, country_codes=["de"])
        ]
        folder = Path(tempfile.mkdtemp(dir=tmp_path / "users"))
        with patch(
            "app.api.v1.routes.users.extract_and_scan",
            return_value=(folder, PS_USER, new_trips),
        ):
            resp = await client.post(
                "/api/v1/users/upload",
                files={"file": ("data.zip", b"fake", "application/zip")},
            )
        assert resp.status_code == 200
        assert resp.json()["trips"][0]["id"] == "trip-2"


class TestUpdateUser:
    async def test_update_locale(self, client: AsyncClient, tmp_path: Path) -> None:
        await sign_in_and_upload(client, tmp_path / "users")
        resp = await client.patch("/api/v1/users", json={"locale": "he-IL"})
        assert resp.status_code == 200
        assert resp.json()["locale"] == "he-IL"


class TestDeleteUser:
    async def test_clears_session(self, client: AsyncClient, tmp_path: Path) -> None:
        await sign_in_and_upload(client, tmp_path / "users")
        resp = await client.delete("/api/v1/users")
        assert resp.status_code == 200
        resp = await client.get("/api/v1/users")
        assert resp.status_code == 401

    async def test_removes_folder(self, client: AsyncClient, tmp_path: Path) -> None:
        user = await sign_in_and_upload(client, tmp_path / "users")
        user_folder = tmp_path / "users" / str(user["id"])
        assert user_folder.exists()
        await client.delete("/api/v1/users")
        assert not user_folder.exists()
