import asyncio
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import ClientDisconnect

from app.logic.chunked_upload import UploadStore
from app.models.processing import UploadSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

MAX_BYTES = 1024 * 1024
OWNER = "test"


async def _one(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def _chunks(count: int, size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    for _ in range(count):
        yield b"\x00" * size


async def _assembled_bytes(
    store: UploadStore, session: AsyncSession, upload_id: str
) -> bytes:
    assembled, _ = await store.assemble(session, upload_id, owner=OWNER)
    try:
        return assembled.read()
    finally:
        assembled.close()


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[UploadStore]:
    store = UploadStore(base=tmp_path / "chunked-uploads")
    async with store.lifespan():
        yield store


class TestWriteChunkStream:
    async def test_chunks_can_continue_on_another_store_instance(
        self, tmp_path: Path, session: AsyncSession
    ) -> None:
        base = tmp_path / "chunked-uploads"
        first = UploadStore(base=base)
        second = UploadStore(base=base)

        async with first.lifespan(), second.lifespan():
            upload_id = await first.create(session, MAX_BYTES, owner=OWNER)
            await second.write_chunk_stream(session, upload_id, 0, _one(b"hello"))

            assert await _assembled_bytes(second, session, upload_id) == b"hello"

    async def test_writes_stream_to_disk(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)

        await store.write_chunk_stream(session, upload_id, 0, _one(b"hello world"))
        assert await _assembled_bytes(store, session, upload_id) == b"hello world"

    async def test_upload_metadata_is_stored_in_db_not_json_manifest(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)

        await store.write_chunk_stream(session, upload_id, 0, _one(b"hello"))

        row = await session.get(UploadSession, upload_id)
        assert row is not None
        assert row.owner == OWNER
        assert row.chunks_written == [0]
        assert not (store._upload_dir(upload_id) / "upload.json").exists()

    @pytest.mark.parametrize("index", [-1, 10_000])
    async def test_rejects_out_of_range_index(
        self, store: UploadStore, session: AsyncSession, index: int
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        with pytest.raises(ValueError, match="out of range"):
            await store.write_chunk_stream(session, upload_id, index, _one(b"x"))

    async def test_rejects_chunk_exceeding_limit_mid_stream(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)

        with pytest.raises(ValueError, match="exceeds"):
            await store.write_chunk_stream(session, upload_id, 0, _chunks(81))

    async def test_tempfile_cleaned_up_on_error(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)

        with pytest.raises(ValueError, match="exceeds"):
            await store.write_chunk_stream(session, upload_id, 0, _chunks(81))

        session_dir = store._upload_dir(upload_id)
        assert list(session_dir.glob("*.part")) == []

    async def test_rejects_accumulated_overflow(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, 100, owner=OWNER)
        await store.write_chunk_stream(session, upload_id, 0, _one(b"\x00" * 90))

        with pytest.raises(OverflowError):
            await store.write_chunk_stream(session, upload_id, 1, _one(b"\x00" * 20))

    async def test_rejects_too_many_chunks(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(session, upload_id, 0, _one(b"a"))
        await store.write_chunk_stream(session, upload_id, 1, _one(b"b"))
        with pytest.raises(ValueError, match="Too many chunks"):
            await store.write_chunk_stream(session, upload_id, 2, _one(b"c"))

    async def test_retry_not_falsely_rejected_by_overflow(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, 100, owner=OWNER)
        await store.write_chunk_stream(session, upload_id, 0, _one(b"\x00" * 90))
        await store.write_chunk_stream(session, upload_id, 0, _one(b"\x00" * 11))

    async def test_idempotent_retry_adjusts_size(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(session, upload_id, 0, _one(b"hello"))
        await store.write_chunk_stream(session, upload_id, 0, _one(b"world!"))
        assert await _assembled_bytes(store, session, upload_id) == b"world!"

    async def test_idempotent_retry_does_not_count_toward_chunk_limit(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(session, upload_id, 0, _one(b"a"))
        await store.write_chunk_stream(session, upload_id, 0, _one(b"a"))
        await store.write_chunk_stream(session, upload_id, 1, _one(b"b"))

    async def test_unknown_session_raises_key_error(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        with pytest.raises(KeyError):
            await store.write_chunk_stream(session, "nonexistent", 0, _one(b"x"))

    async def test_client_disconnect_propagates(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)

        async def gen() -> AsyncIterator[bytes]:
            yield b"partial"
            raise ClientDisconnect

        with pytest.raises(ClientDisconnect):
            await store.write_chunk_stream(session, upload_id, 0, gen())

        session_dir = store._upload_dir(upload_id)
        assert list(session_dir.glob("*.part")) == []

    async def test_concurrent_same_index_writes_do_not_corrupt(
        self, store: UploadStore, session: AsyncSession, engine: AsyncEngine
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        await session.commit()

        async def write(data: bytes) -> None:
            async with AsyncSession(engine, expire_on_commit=False) as write_session:
                await store.write_chunk_stream(write_session, upload_id, 0, _one(data))
                await write_session.commit()

        await asyncio.gather(
            write(b"AAAA"),
            write(b"BBBB"),
        )

        assert await _assembled_bytes(store, session, upload_id) in (b"AAAA", b"BBBB")

    async def test_concurrent_different_index_writes(
        self, store: UploadStore, session: AsyncSession, engine: AsyncEngine
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        await session.commit()

        async def write(index: int, data: bytes) -> None:
            async with AsyncSession(engine, expire_on_commit=False) as write_session:
                await store.write_chunk_stream(
                    write_session, upload_id, index, _one(data)
                )
                await write_session.commit()

        await asyncio.gather(
            write(0, b"AAA"),
            write(1, b"BBB"),
        )

        assert await _assembled_bytes(store, session, upload_id) == b"AAABBB"


class TestAssemble:
    async def test_chunks_concatenated_in_order(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(session, upload_id, 1, _one(b"BBB"))
        await store.write_chunk_stream(session, upload_id, 0, _one(b"AAA"))

        assert await _assembled_bytes(store, session, upload_id) == b"AAABBB"

    async def test_no_chunks_raises(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        with pytest.raises(ValueError, match="No chunks"):
            await store.assemble(session, upload_id, owner=OWNER)

    async def test_unknown_session_raises_key_error(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        with pytest.raises(KeyError):
            await store.assemble(session, "nonexistent", owner=OWNER)

    async def test_session_removed_after_assemble(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(session, upload_id, 0, _one(b"x"))
        assembled, _ = await store.assemble(session, upload_id, owner=OWNER)
        assembled.close()
        with pytest.raises(KeyError):
            await store.assemble(session, upload_id, owner=OWNER)

    async def test_wrong_owner_raises_permission_error(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner="alice")
        await store.write_chunk_stream(session, upload_id, 0, _one(b"x"))
        with pytest.raises(PermissionError, match="different user"):
            await store.assemble(session, upload_id, owner="bob")

    async def test_non_contiguous_chunks_raises(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(session, upload_id, 0, _one(b"AAA"))
        await store.write_chunk_stream(session, upload_id, 2, _one(b"CCC"))
        with pytest.raises(ValueError, match="not contiguous"):
            await store.assemble(session, upload_id, owner=OWNER)

    async def test_assemble_ignores_orphan_part_files(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(session, upload_id, 0, _one(b"real"))
        session_dir = store._upload_dir(upload_id)
        (session_dir / f"0000.{'ab' * 8}.part").write_bytes(b"STALE")

        assert await _assembled_bytes(store, session, upload_id) == b"real"

    async def test_assemble_ignores_uncommitted_final_chunk(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(session, upload_id, 0, _one(b"committed"))
        session_dir = store._upload_dir(upload_id)
        (session_dir / "0001").write_bytes(b"STALE")

        assert await _assembled_bytes(store, session, upload_id) == b"committed"


class TestEviction:
    async def test_expired_session_is_cleaned_up(
        self, tmp_path: Path, session: AsyncSession
    ) -> None:
        store = UploadStore(base=tmp_path / "chunked-uploads")
        async with store.lifespan():
            upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
            await store.write_chunk_stream(session, upload_id, 0, _one(b"data"))

            await store._evict(session, upload_id)

            with pytest.raises(KeyError):
                await store.assemble(session, upload_id, owner=OWNER)

    async def test_abandoned_session_expires_when_cleanup_runs(
        self, tmp_path: Path, session: AsyncSession
    ) -> None:
        store = UploadStore(base=tmp_path / "chunked-uploads")
        async with store.lifespan():
            upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
            row = await session.get_one(UploadSession, upload_id)
            row.expires_at = row.created_at
            session.add(row)
            await session.flush()

            await store.cleanup_expired(session)

            with pytest.raises(KeyError):
                await store.assemble(session, upload_id, owner=OWNER)

    async def test_eviction_during_write_surfaces_as_key_error(
        self, store: UploadStore, session: AsyncSession
    ) -> None:
        upload_id = await store.create(session, MAX_BYTES, owner=OWNER)
        session_dir = store._upload_dir(upload_id)

        async def gen() -> AsyncIterator[bytes]:
            shutil.rmtree(session_dir)
            yield b"doomed"

        with pytest.raises(KeyError):
            await store.write_chunk_stream(session, upload_id, 0, gen())
