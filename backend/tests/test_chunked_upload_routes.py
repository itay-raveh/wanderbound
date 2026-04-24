"""Integration tests for the chunked upload endpoints (init/chunk/complete)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from starlette.requests import ClientDisconnect

from app.core.config import get_settings
from app.logic.chunked_upload import upload_store

from .factories import mock_extract, sign_in, sign_in_and_upload

if TYPE_CHECKING:
    from httpx import AsyncClient


async def _init(client: AsyncClient, provider: str = "google") -> str:
    """Sign in then POST /upload/init, return upload_id."""
    await sign_in(client, provider)
    resp = await client.post("/api/v1/users/upload/init")
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
        with mock_extract(users_dir):
            complete = await client.post(
                f"/api/v1/users/upload/{upload_id}/complete",
            )
        assert complete.status_code == 200

    async def test_client_disconnect_returns_quietly(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Browser abort mid-upload should not produce a 500 traceback."""
        upload_id = await _init(client)

        async def raise_disconnect(*_args: object, **_kwargs: object) -> None:
            raise ClientDisconnect

        monkeypatch.setattr(upload_store, "write_chunk_stream", raise_disconnect)

        resp = await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"anything",
        )
        assert resp.status_code == 204

    async def test_rejects_overflow(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Accumulated chunks exceeding max_bytes return 413."""
        # Set a tiny limit so a small chunk triggers overflow
        monkeypatch.setattr(get_settings(), "VITE_MAX_UPLOAD_GB", 0)
        await sign_in(client)
        init_resp = await client.post("/api/v1/users/upload/init")
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
        with mock_extract(users_dir):
            resp = await client.post(
                f"/api/v1/users/upload/{upload_id}/complete",
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["id"] == 999
        assert len(body["trips"]) == 1

    async def test_rejects_unknown_session(self, client: AsyncClient) -> None:
        await sign_in(client)
        resp = await client.post("/api/v1/users/upload/nonexistent/complete")
        assert resp.status_code == 404

    async def test_rejects_empty_upload(self, client: AsyncClient) -> None:
        upload_id = await _init(client)
        resp = await client.post(f"/api/v1/users/upload/{upload_id}/complete")
        assert resp.status_code == 400

    async def test_rejects_unauthenticated(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/users/upload/any-id/complete")
        assert resp.status_code == 401

    async def test_bad_zip_returns_406(self, client: AsyncClient) -> None:
        """Assembled chunks that aren't a valid ZIP should return 406."""
        upload_id = await _init(client)
        await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"not a zip at all",
        )
        resp = await client.post(f"/api/v1/users/upload/{upload_id}/complete")
        assert resp.status_code == 406

    @pytest.mark.parametrize("provider", ["google", "microsoft"])
    async def test_both_providers(
        self, client: AsyncClient, tmp_path: Path, provider: str
    ) -> None:
        """Chunked upload works with both Google and Microsoft auth."""
        upload_id = await _init(client, provider=provider)

        await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"fake-zip",
        )

        users_dir = tmp_path / "users"
        users_dir.mkdir(exist_ok=True)
        with mock_extract(users_dir):
            resp = await client.post(
                f"/api/v1/users/upload/{upload_id}/complete",
            )
        assert resp.status_code == 200

    async def test_reupload_via_session_cookie(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """Logged-in user can re-upload without credential/provider."""
        users_dir = tmp_path / "users"
        users_dir.mkdir(exist_ok=True)
        await sign_in_and_upload(client, users_dir)

        init_resp = await client.post("/api/v1/users/upload/init")
        assert init_resp.status_code == 200
        upload_id = init_resp.json()["upload_id"]

        await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"fake-zip",
        )

        with mock_extract(users_dir):
            resp = await client.post(
                f"/api/v1/users/upload/{upload_id}/complete",
            )
        assert resp.status_code == 200
        assert resp.json()["user"]["id"] == 999

    async def test_rejects_wrong_owner(self, client: AsyncClient) -> None:
        """Complete by a different user than init returns 403."""
        # Init as Google user (owner = "google:google-123")
        upload_id = await _init(client)
        await client.put(
            f"/api/v1/users/upload/{upload_id}/0",
            content=b"chunk",
        )
        await sign_in(client, provider="microsoft")
        resp = await client.post(f"/api/v1/users/upload/{upload_id}/complete")
        assert resp.status_code == 403


class TestParallelChunkedUpload:
    async def test_parallel_chunks_complete_cleanly(
        self, client: AsyncClient, tmp_path: Path
    ) -> None:
        """4 concurrent PUTs to one session finish and complete succeeds."""
        upload_id = await _init(client)

        async def put_chunk(index: int, data: bytes) -> None:
            resp = await client.put(
                f"/api/v1/users/upload/{upload_id}/{index}",
                content=data,
            )
            assert resp.status_code == 204

        await asyncio.gather(
            *(
                put_chunk(i, p)
                for i, p in enumerate([b"AAAA", b"BBBB", b"CCCC", b"DDDD"])
            )
        )

        users_dir = tmp_path / "users"
        users_dir.mkdir(exist_ok=True)
        with mock_extract(users_dir):
            resp = await client.post(
                f"/api/v1/users/upload/{upload_id}/complete",
            )
        assert resp.status_code == 200
