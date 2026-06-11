from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from starlette.requests import ClientDisconnect

from app.core.config import get_settings
from app.logic.chunked_upload import upload_store

from .helpers.users import UserRoutes

if TYPE_CHECKING:
    from pathlib import Path

    from sqlmodel.ext.asyncio.session import AsyncSession


class TestInitChunkedUpload:
    async def test_returns_upload_id(self, user_routes: UserRoutes) -> None:
        upload_id = await user_routes.start_chunked_upload()
        assert isinstance(upload_id, str)
        assert len(upload_id) > 10  # token_urlsafe produces ~43 chars

    async def test_rejects_unauthenticated(self, user_routes: UserRoutes) -> None:
        resp = await user_routes.init_upload()
        assert resp.status_code == 401


class TestUploadChunk:
    async def test_accepts_valid_chunk(self, user_routes: UserRoutes) -> None:
        upload_id = await user_routes.start_chunked_upload()
        await user_routes.put_chunk_ok(upload_id, 0, b"chunk-data")

    async def test_init_is_committed_before_chunk_request(
        self, user_routes: UserRoutes, session: AsyncSession
    ) -> None:
        upload_id = await user_routes.start_chunked_upload()
        await session.rollback()

        await user_routes.put_chunk_ok(upload_id, 0, b"chunk-data")

    async def test_rejects_unknown_session(self, user_routes: UserRoutes) -> None:
        resp = await user_routes.put_chunk("nonexistent", 0, b"chunk-data")
        assert resp.status_code == 404

    async def test_rejects_negative_index(self, user_routes: UserRoutes) -> None:
        upload_id = await user_routes.start_chunked_upload()
        resp = await user_routes.put_chunk(upload_id, -1, b"x")
        assert resp.status_code == 400

    async def test_idempotent_retry(
        self, user_routes: UserRoutes, users_dir: Path
    ) -> None:
        upload_id = await user_routes.start_chunked_upload()

        await user_routes.put_chunk_ok(upload_id, 0, b"first-attempt")
        await user_routes.put_chunk_ok(upload_id, 0, b"retry-attempt")

        await user_routes.complete_upload_with_extract_ok(upload_id, users_dir)

    async def test_client_disconnect_returns_quietly(
        self, user_routes: UserRoutes, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        upload_id = await user_routes.start_chunked_upload()

        async def raise_disconnect(*_args: object, **_kwargs: object) -> None:
            raise ClientDisconnect

        monkeypatch.setattr(upload_store, "write_chunk_stream", raise_disconnect)

        resp = await user_routes.put_chunk(upload_id, 0, b"anything")
        assert resp.status_code == 204

    async def test_rejects_overflow(
        self,
        user_routes: UserRoutes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(get_settings(), "VITE_MAX_UPLOAD_GB", 0)
        await user_routes.sign_in()
        init_resp = await user_routes.init_upload()
        upload_id = init_resp.json()["upload_id"]

        resp = await user_routes.put_chunk(upload_id, 0, b"any data at all")
        assert resp.status_code == 413


class TestCompleteChunkedUpload:
    async def test_happy_path(self, user_routes: UserRoutes, users_dir: Path) -> None:
        upload_id = await user_routes.start_chunked_upload()

        await user_routes.put_chunk_ok(upload_id, 0, b"fake-zip-part1")
        await user_routes.put_chunk_ok(upload_id, 1, b"fake-zip-part2")

        body = await user_routes.complete_upload_with_extract_ok(upload_id, users_dir)
        assert body["user"]["id"] == 999
        assert len(body["trips"]) == 1

    async def test_chunk_is_committed_before_complete_request(
        self,
        user_routes: UserRoutes,
        users_dir: Path,
        session: AsyncSession,
    ) -> None:
        upload_id = await user_routes.start_chunked_upload()
        await user_routes.put_chunk_ok(upload_id, 0, b"fake-zip")
        await session.rollback()

        body = await user_routes.complete_upload_with_extract_ok(upload_id, users_dir)
        assert body["user"]["id"] == 999

    async def test_rejects_unknown_session(self, user_routes: UserRoutes) -> None:
        await user_routes.sign_in()
        resp = await user_routes.complete_upload("nonexistent")
        assert resp.status_code == 404

    async def test_rejects_empty_upload(self, user_routes: UserRoutes) -> None:
        upload_id = await user_routes.start_chunked_upload()
        resp = await user_routes.complete_upload(upload_id)
        assert resp.status_code == 400

    async def test_rejects_unauthenticated(self, user_routes: UserRoutes) -> None:
        resp = await user_routes.complete_upload("any-id")
        assert resp.status_code == 401

    async def test_bad_zip_returns_406(self, user_routes: UserRoutes) -> None:
        upload_id = await user_routes.start_chunked_upload()
        await user_routes.put_chunk(upload_id, 0, b"not a zip at all")
        resp = await user_routes.complete_upload(upload_id)
        assert resp.status_code == 406

    @pytest.mark.parametrize("provider", ["google", "microsoft"])
    async def test_both_providers(
        self, user_routes: UserRoutes, users_dir: Path, provider: str
    ) -> None:
        upload_id = await user_routes.start_chunked_upload(provider=provider)

        await user_routes.put_chunk_ok(upload_id, 0)

        await user_routes.complete_upload_with_extract_ok(upload_id, users_dir)

    @pytest.mark.usefixtures("uploaded_user")
    async def test_reupload_via_session_cookie(
        self, user_routes: UserRoutes, users_dir: Path
    ) -> None:
        init_resp = await user_routes.init_upload()
        assert init_resp.status_code == 200
        upload_id = init_resp.json()["upload_id"]

        await user_routes.put_chunk_ok(upload_id, 0)

        body = await user_routes.complete_upload_with_extract_ok(upload_id, users_dir)
        assert body["user"]["id"] == 999

    async def test_rejects_wrong_owner(self, user_routes: UserRoutes) -> None:
        upload_id = await user_routes.start_chunked_upload()
        await user_routes.put_chunk_ok(upload_id, 0, b"chunk")
        await user_routes.sign_in(provider="microsoft")
        resp = await user_routes.complete_upload(upload_id)
        assert resp.status_code == 403


class TestParallelChunkedUpload:
    async def test_parallel_chunks_complete_cleanly(
        self, user_routes: UserRoutes, users_dir: Path
    ) -> None:
        upload_id = await user_routes.start_chunked_upload()

        await asyncio.gather(
            *(
                user_routes.put_chunk_ok(upload_id, i, p)
                for i, p in enumerate([b"AAAA", b"BBBB", b"CCCC", b"DDDD"])
            )
        )

        await user_routes.complete_upload_with_extract_ok(upload_id, users_dir)
