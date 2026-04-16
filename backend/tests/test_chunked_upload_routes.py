"""Integration tests for the chunked upload endpoints (init/chunk/complete)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.core.config import get_settings

from .factories import mock_extract, mock_jwt

if TYPE_CHECKING:
    from httpx import AsyncClient


async def _init(client: AsyncClient) -> str:
    """POST /upload/init with mocked Google auth, return upload_id."""
    with mock_jwt("google"):
        resp = await client.post(
            "/api/v1/users/upload/init",
            data={"credential": "fake", "provider": "google"},
        )
    assert resp.status_code == 200
    return resp.json()["upload_id"]


class TestInitChunkedUpload:
    async def test_returns_upload_id(self, client: AsyncClient) -> None:
        upload_id = await _init(client)
        assert isinstance(upload_id, str)
        assert len(upload_id) > 10  # token_urlsafe produces ~43 chars

    async def test_rejects_unauthenticated(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/users/upload/init")
        assert resp.status_code == 401


class TestUploadChunk:
    async def test_accepts_valid_chunk(self, client: AsyncClient) -> None:
        upload_id = await _init(client)
        resp = await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"chunk-data",
        )
        assert resp.status_code == 204

    async def test_rejects_unknown_session(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/v1/users/upload/nonexistent/0",
            content=b"chunk-data",
        )
        assert resp.status_code == 404

    async def test_rejects_negative_index(self, client: AsyncClient) -> None:
        upload_id = await _init(client)
        resp = await client.put(
            f"/api/v1/users/upload/{upload_id}/-1",
            content=b"x",
        )
        assert resp.status_code == 400

    async def test_idempotent_retry(self, client: AsyncClient, tmp_path: Path) -> None:
        """Re-uploading the same chunk index uses the latest data."""
        upload_id = await _init(client)

        await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"first-attempt",
        )
        resp = await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"retry-attempt",
        )
        assert resp.status_code == 204

        users_dir = tmp_path / "users"
        users_dir.mkdir(exist_ok=True)
        with mock_jwt("google"), mock_extract(users_dir):
            complete = await client.post(
                f"/api/v1/users/upload/{upload_id}/complete",
                data={"credential": "fake", "provider": "google"},
            )
        assert complete.status_code == 200

    async def test_rejects_overflow(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Accumulated chunks exceeding max_bytes return 413."""
        # Set a tiny limit so a small chunk triggers overflow
        monkeypatch.setattr(get_settings(), "VITE_MAX_UPLOAD_GB", 0)
        with mock_jwt("google"):
            init_resp = await client.post(
                "/api/v1/users/upload/init",
                data={"credential": "fake", "provider": "google"},
            )
        upload_id = init_resp.json()["upload_id"]

        resp = await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"any data at all",
        )
        assert resp.status_code == 413


class TestCompleteChunkedUpload:
    async def test_happy_path(self, client: AsyncClient, tmp_path: Path) -> None:
        upload_id = await _init(client)

        await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"fake-zip-part1",
        )
        await client.put(
            f"/api/v1/users/upload/{upload_id}/1",
            content=b"fake-zip-part2",
        )

        users_dir = tmp_path / "users"
        users_dir.mkdir(exist_ok=True)
        with mock_jwt("google"), mock_extract(users_dir):
            resp = await client.post(
                f"/api/v1/users/upload/{upload_id}/complete",
                data={"credential": "fake", "provider": "google"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["id"] == 999
        assert len(body["trips"]) == 1

    async def test_rejects_unknown_session(self, client: AsyncClient) -> None:
        with mock_jwt("google"):
            resp = await client.post(
                "/api/v1/users/upload/nonexistent/complete",
                data={"credential": "fake", "provider": "google"},
            )
        assert resp.status_code == 404

    async def test_rejects_empty_upload(self, client: AsyncClient) -> None:
        upload_id = await _init(client)
        # Complete without uploading any chunks
        with mock_jwt("google"):
            resp = await client.post(
                f"/api/v1/users/upload/{upload_id}/complete",
                data={"credential": "fake", "provider": "google"},
            )
        assert resp.status_code == 400

    async def test_rejects_unauthenticated(self, client: AsyncClient) -> None:
        upload_id = await _init(client)
        resp = await client.post(
            f"/api/v1/users/upload/{upload_id}/complete",
        )
        assert resp.status_code == 401

    async def test_bad_zip_returns_406(self, client: AsyncClient) -> None:
        """Assembled chunks that aren't a valid ZIP should return 406."""
        upload_id = await _init(client)
        await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"not a zip at all",
        )
        with mock_jwt("google"):
            resp = await client.post(
                f"/api/v1/users/upload/{upload_id}/complete",
                data={"credential": "fake", "provider": "google"},
            )
        assert resp.status_code == 406

    @pytest.mark.parametrize("provider", ["google", "microsoft"])
    async def test_both_providers(
        self, client: AsyncClient, tmp_path: Path, provider: str
    ) -> None:
        """Chunked upload works with both Google and Microsoft auth."""
        with mock_jwt(provider):
            init_resp = await client.post(
                "/api/v1/users/upload/init",
                data={"credential": "fake", "provider": provider},
            )
        upload_id = init_resp.json()["upload_id"]

        await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"fake-zip",
        )

        users_dir = tmp_path / "users"
        users_dir.mkdir(exist_ok=True)
        with mock_jwt(provider), mock_extract(users_dir):
            resp = await client.post(
                f"/api/v1/users/upload/{upload_id}/complete",
                data={"credential": "fake", "provider": provider},
            )
        assert resp.status_code == 200

    async def test_rejects_wrong_owner(self, client: AsyncClient) -> None:
        """Complete by a different user than init returns 403."""
        # Init as Google user (owner = "google:google-123")
        upload_id = await _init(client)
        await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"chunk",
        )
        # Complete as Microsoft user (owner = "microsoft:microsoft-456")
        with mock_jwt("microsoft"):
            resp = await client.post(
                f"/api/v1/users/upload/{upload_id}/complete",
                data={"credential": "fake", "provider": "microsoft"},
            )
        assert resp.status_code == 403
