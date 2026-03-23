from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from app.logic.upload import TripMeta

from .conftest import (
    GOOGLE_PAYLOAD,
    PS_USER,
    mock_extract,
    mock_jwt,
    sign_in_and_upload,
)

if TYPE_CHECKING:
    from httpx import AsyncClient


class TestAuthGoogle:
    async def test_invalid_jwt(self, client: AsyncClient) -> None:
        with mock_jwt(decode_error=True):
            resp = await client.post("/api/v1/auth/google", json={"credential": "bad"})
        assert resp.status_code == 401

    async def test_new_user_returns_null(self, client: AsyncClient) -> None:
        with mock_jwt():
            resp = await client.post("/api/v1/auth/google", json={"credential": "fake"})
        assert resp.status_code == 200
        assert resp.json() is None

    async def test_existing_user_returns_user(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        await sign_in_and_upload(client, tmp_path / "users")
        await client.post("/api/v1/auth/logout")

        with mock_jwt():
            resp = await client.post("/api/v1/auth/google", json={"credential": "fake"})
        assert resp.status_code == 200
        user = resp.json()
        assert user is not None
        assert user["google_sub"] == "google-123"


class TestLogout:
    async def test_clears_session(self, client: AsyncClient, tmp_path: Path) -> None:
        await sign_in_and_upload(client, tmp_path / "users")
        await client.post("/api/v1/auth/logout")
        resp = await client.get("/api/v1/users")
        assert resp.status_code == 401


class TestReadUser:
    async def test_unauthenticated(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/users")
        assert resp.status_code == 401

    async def test_authenticated(self, client: AsyncClient, tmp_path: Path) -> None:
        await sign_in_and_upload(client, tmp_path / "users")
        resp = await client.get("/api/v1/users")
        assert resp.status_code == 200
        assert resp.json()["first_name"] == "Test"


class TestUpload:
    async def test_no_session(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/users/upload",
            files={"file": ("data.zip", b"fake", "application/zip")},
        )
        assert resp.status_code == 401

    async def test_new_user(self, client: AsyncClient, tmp_path: Path) -> None:
        user = await sign_in_and_upload(client, tmp_path / "users")
        assert user["google_sub"] == "google-123"
        assert user["first_name"] == "Test"  # Google name preferred over ZIP

    async def test_falls_back_to_zip_name(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        no_name = {**GOOGLE_PAYLOAD, "given_name": "", "family_name": ""}
        with mock_jwt(no_name), mock_extract(tmp_path / "users"):
            resp = await client.post(
                "/api/v1/users/upload",
                data={"credential": "fake"},
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

    async def test_creates_user_folder(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        user = await sign_in_and_upload(client, tmp_path / "users")
        assert (tmp_path / "users" / str(user["id"])).exists()


class TestUpdateUser:
    async def test_update_locale(self, client: AsyncClient, tmp_path: Path) -> None:
        await sign_in_and_upload(client, tmp_path / "users")
        resp = await client.patch("/api/v1/users", json={"locale": "he-IL"})
        assert resp.status_code == 200
        assert resp.json()["locale"] == "he-IL"

    async def test_partial_update(self, client: AsyncClient, tmp_path: Path) -> None:
        await sign_in_and_upload(client, tmp_path / "users")
        resp = await client.patch("/api/v1/users", json={"unit_is_km": False})
        assert resp.status_code == 200
        user = resp.json()
        assert user["unit_is_km"] is False
        assert user["first_name"] == "Test"  # unchanged


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
