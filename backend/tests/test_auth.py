"""Tests for auth and user management endpoints."""

import tempfile
from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt as jwt_module
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.deps import _get_session
from app.core.config import get_settings
from app.logic.upload import TripMeta
from app.main import app
from app.models.user import PSUser

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


async def _test_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSession(_engine, expire_on_commit=False) as session:
        yield session


GOOGLE_PAYLOAD = {
    "sub": "google-123",
    "given_name": "Test",
    "family_name": "User",
    "picture": "https://example.com/photo.jpg",
}

PS_USER = PSUser(
    id=999,
    first_name="Zip",
    last_name="User",
    locale="en-US",
    unit_is_km=True,
    temperature_is_celsius=True,
)

TRIPS = [TripMeta(id="trip-1", title="Test Trip", step_count=5, country_codes=["nl"])]


@contextmanager
def mock_jwt(
    payload: dict | None = None, *, decode_error: bool = False
) -> Generator[None]:
    """Patch Google JWT verification to return the given payload (or raise)."""
    mock_key = MagicMock()
    mock_key.key = "fake-key"
    decode_kwargs: dict = (
        {"side_effect": jwt_module.InvalidTokenError}
        if decode_error
        else {"return_value": payload or GOOGLE_PAYLOAD}
    )
    with (
        patch(
            "app.api.v1.routes.auth._jwks_client.get_signing_key_from_jwt",
            return_value=mock_key,
        ),
        patch("jwt.decode", **decode_kwargs),
    ):
        yield


def mock_extract(users_dir: Path) -> patch:
    """Patch extract_and_scan to return test data with a real temp folder."""
    folder = Path(tempfile.mkdtemp(dir=users_dir))
    return patch(
        "app.api.v1.routes.users.extract_and_scan",
        return_value=(folder, PS_USER, TRIPS),
    )


@pytest.fixture(autouse=True)
async def _setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[None]:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    (tmp_path / "users").mkdir()
    app.dependency_overrides[_get_session] = _test_session
    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    app.dependency_overrides.clear()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


async def _sign_in_and_upload(client: AsyncClient, users_dir: Path) -> dict:
    """Sign in as new Google user, upload ZIP with credential, return user dict."""
    with mock_jwt(), mock_extract(users_dir):
        resp = await client.post(
            "/api/v1/users/upload",
            data={"credential": "fake"},
            files={"file": ("data.zip", b"fake", "application/zip")},
        )
    assert resp.status_code == 200
    return resp.json()["user"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestAuthGoogle:
    @pytest.mark.anyio
    async def test_invalid_jwt(self, client: AsyncClient) -> None:
        with mock_jwt(decode_error=True):
            resp = await client.post("/api/v1/auth/google", json={"credential": "bad"})
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_new_user_returns_null(self, client: AsyncClient) -> None:
        with mock_jwt():
            resp = await client.post("/api/v1/auth/google", json={"credential": "fake"})
        assert resp.status_code == 200
        assert resp.json() is None

    @pytest.mark.anyio
    async def test_existing_user_returns_user(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        await _sign_in_and_upload(client, tmp_path / "users")
        await client.post("/api/v1/auth/logout")

        with mock_jwt():
            resp = await client.post("/api/v1/auth/google", json={"credential": "fake"})
        assert resp.status_code == 200
        user = resp.json()
        assert user is not None
        assert user["google_sub"] == "google-123"


class TestLogout:
    @pytest.mark.anyio
    async def test_clears_session(self, client: AsyncClient, tmp_path: Path) -> None:
        await _sign_in_and_upload(client, tmp_path / "users")
        await client.post("/api/v1/auth/logout")
        resp = await client.get("/api/v1/users")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class TestReadUser:
    @pytest.mark.anyio
    async def test_unauthenticated(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/users")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_authenticated(self, client: AsyncClient, tmp_path: Path) -> None:
        await _sign_in_and_upload(client, tmp_path / "users")
        resp = await client.get("/api/v1/users")
        assert resp.status_code == 200
        assert resp.json()["first_name"] == "Test"


class TestUpload:
    @pytest.mark.anyio
    async def test_no_session(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/users/upload",
            files={"file": ("data.zip", b"fake", "application/zip")},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_new_user(self, client: AsyncClient, tmp_path: Path) -> None:
        user = await _sign_in_and_upload(client, tmp_path / "users")
        assert user["google_sub"] == "google-123"
        assert user["first_name"] == "Test"  # Google name preferred over ZIP

    @pytest.mark.anyio
    async def test_falls_back_to_zip_name(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """When Google identity has empty names, use names from the ZIP."""
        no_name = {**GOOGLE_PAYLOAD, "given_name": "", "family_name": ""}
        with mock_jwt(no_name), mock_extract(tmp_path / "users"):
            resp = await client.post(
                "/api/v1/users/upload",
                data={"credential": "fake"},
                files={"file": ("data.zip", b"fake", "application/zip")},
            )
        user = resp.json()["user"]
        assert user["first_name"] == "Zip"
        assert user["last_name"] == "User"

    @pytest.mark.anyio
    async def test_reupload_updates_trips(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        await _sign_in_and_upload(client, tmp_path / "users")

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

    @pytest.mark.anyio
    async def test_creates_user_folder(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        user = await _sign_in_and_upload(client, tmp_path / "users")
        assert (tmp_path / "users" / str(user["id"])).exists()


class TestUpdateUser:
    @pytest.mark.anyio
    async def test_update_locale(self, client: AsyncClient, tmp_path: Path) -> None:
        await _sign_in_and_upload(client, tmp_path / "users")
        resp = await client.patch("/api/v1/users", json={"locale": "he-IL"})
        assert resp.status_code == 200
        assert resp.json()["locale"] == "he-IL"

    @pytest.mark.anyio
    async def test_partial_update(self, client: AsyncClient, tmp_path: Path) -> None:
        await _sign_in_and_upload(client, tmp_path / "users")
        resp = await client.patch("/api/v1/users", json={"unit_is_km": False})
        assert resp.status_code == 200
        user = resp.json()
        assert user["unit_is_km"] is False
        assert user["first_name"] == "Test"  # unchanged


class TestDeleteUser:
    @pytest.mark.anyio
    async def test_clears_session(self, client: AsyncClient, tmp_path: Path) -> None:
        await _sign_in_and_upload(client, tmp_path / "users")
        resp = await client.delete("/api/v1/users")
        assert resp.status_code == 200
        resp = await client.get("/api/v1/users")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_removes_folder(self, client: AsyncClient, tmp_path: Path) -> None:
        user = await _sign_in_and_upload(client, tmp_path / "users")
        user_folder = tmp_path / "users" / str(user["id"])
        assert user_folder.exists()
        await client.delete("/api/v1/users")
        assert not user_folder.exists()
