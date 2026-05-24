import asyncio
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from starlette.requests import ClientDisconnect

from app.logic.chunked_upload import UploadStore

MAX_BYTES = 1024 * 1024
OWNER = "test"


async def _one(data: bytes) -> AsyncIterator[bytes]:
    yield data


async def _chunks(count: int, size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    for _ in range(count):
        yield b"\x00" * size


def _assembled_bytes(store: UploadStore, upload_id: str) -> bytes:
    assembled, _ = store.assemble(upload_id, owner=OWNER)
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
        self, tmp_path: Path
    ) -> None:
        base = tmp_path / "chunked-uploads"
        first = UploadStore(base=base)
        second = UploadStore(base=base)

        async with first.lifespan(), second.lifespan():
            upload_id = first.create(MAX_BYTES, owner=OWNER)
            await second.write_chunk_stream(upload_id, 0, _one(b"hello"))

            assert _assembled_bytes(second, upload_id) == b"hello"

    async def test_writes_stream_to_disk(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)

        await store.write_chunk_stream(upload_id, 0, _one(b"hello world"))
        assert _assembled_bytes(store, upload_id) == b"hello world"

    @pytest.mark.parametrize("index", [-1, 10_000])
    async def test_rejects_out_of_range_index(
        self, store: UploadStore, index: int
    ) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)
        with pytest.raises(ValueError, match="out of range"):
            await store.write_chunk_stream(upload_id, index, _one(b"x"))

    async def test_rejects_chunk_exceeding_limit_mid_stream(
        self, store: UploadStore
    ) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)

        with pytest.raises(ValueError, match="exceeds"):
            await store.write_chunk_stream(upload_id, 0, _chunks(81))

    async def test_tempfile_cleaned_up_on_error(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)

        with pytest.raises(ValueError, match="exceeds"):
            await store.write_chunk_stream(upload_id, 0, _chunks(81))

        session_dir = store._upload_dir(upload_id)
        assert list(session_dir.glob("*.part")) == []

    async def test_rejects_accumulated_overflow(self, store: UploadStore) -> None:
        upload_id = store.create(100, owner=OWNER)
        await store.write_chunk_stream(upload_id, 0, _one(b"\x00" * 90))

        with pytest.raises(OverflowError):
            await store.write_chunk_stream(upload_id, 1, _one(b"\x00" * 20))

    async def test_rejects_too_many_chunks(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(upload_id, 0, _one(b"a"))
        await store.write_chunk_stream(upload_id, 1, _one(b"b"))
        with pytest.raises(ValueError, match="Too many chunks"):
            await store.write_chunk_stream(upload_id, 2, _one(b"c"))

    async def test_retry_not_falsely_rejected_by_overflow(
        self, store: UploadStore
    ) -> None:
        upload_id = store.create(100, owner=OWNER)
        await store.write_chunk_stream(upload_id, 0, _one(b"\x00" * 90))
        await store.write_chunk_stream(upload_id, 0, _one(b"\x00" * 11))

    async def test_idempotent_retry_adjusts_size(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(upload_id, 0, _one(b"hello"))
        await store.write_chunk_stream(upload_id, 0, _one(b"world!"))
        assert _assembled_bytes(store, upload_id) == b"world!"

    async def test_idempotent_retry_does_not_count_toward_chunk_limit(
        self, store: UploadStore
    ) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(upload_id, 0, _one(b"a"))
        await store.write_chunk_stream(upload_id, 0, _one(b"a"))
        await store.write_chunk_stream(upload_id, 1, _one(b"b"))

    async def test_unknown_session_raises_key_error(self, store: UploadStore) -> None:
        with pytest.raises(KeyError):
            await store.write_chunk_stream("nonexistent", 0, _one(b"x"))

    async def test_client_disconnect_propagates(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)

        async def gen() -> AsyncIterator[bytes]:
            yield b"partial"
            raise ClientDisconnect

        with pytest.raises(ClientDisconnect):
            await store.write_chunk_stream(upload_id, 0, gen())

        session_dir = store._upload_dir(upload_id)
        assert list(session_dir.glob("*.part")) == []

    async def test_concurrent_same_index_writes_do_not_corrupt(
        self, store: UploadStore
    ) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)

        await asyncio.gather(
            store.write_chunk_stream(upload_id, 0, _one(b"AAAA")),
            store.write_chunk_stream(upload_id, 0, _one(b"BBBB")),
        )

        assert _assembled_bytes(store, upload_id) in (b"AAAA", b"BBBB")

    async def test_concurrent_different_index_writes(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)

        await asyncio.gather(
            store.write_chunk_stream(upload_id, 0, _one(b"AAA")),
            store.write_chunk_stream(upload_id, 1, _one(b"BBB")),
            store.write_chunk_stream(upload_id, 2, _one(b"CCC")),
        )

        assert _assembled_bytes(store, upload_id) == b"AAABBBCCC"


class TestAssemble:
    async def test_chunks_concatenated_in_order(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(upload_id, 1, _one(b"BBB"))
        await store.write_chunk_stream(upload_id, 0, _one(b"AAA"))

        assert _assembled_bytes(store, upload_id) == b"AAABBB"

    async def test_no_chunks_raises(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)
        with pytest.raises(ValueError, match="No chunks"):
            store.assemble(upload_id, owner=OWNER)

    async def test_unknown_session_raises_key_error(self, store: UploadStore) -> None:
        with pytest.raises(KeyError):
            store.assemble("nonexistent", owner=OWNER)

    async def test_session_removed_after_assemble(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(upload_id, 0, _one(b"x"))
        assembled, _ = store.assemble(upload_id, owner=OWNER)
        assembled.close()
        with pytest.raises(KeyError):
            store.assemble(upload_id, owner=OWNER)

    async def test_wrong_owner_raises_permission_error(
        self, store: UploadStore
    ) -> None:
        upload_id = store.create(MAX_BYTES, owner="alice")
        await store.write_chunk_stream(upload_id, 0, _one(b"x"))
        with pytest.raises(PermissionError, match="different user"):
            store.assemble(upload_id, owner="bob")

    async def test_non_contiguous_chunks_raises(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(upload_id, 0, _one(b"AAA"))
        await store.write_chunk_stream(upload_id, 2, _one(b"CCC"))
        with pytest.raises(ValueError, match="not contiguous"):
            store.assemble(upload_id, owner=OWNER)

    async def test_assemble_ignores_orphan_part_files(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)
        await store.write_chunk_stream(upload_id, 0, _one(b"real"))
        session_dir = store._upload_dir(upload_id)
        (session_dir / f"0000.{'ab' * 8}.part").write_bytes(b"STALE")

        assert _assembled_bytes(store, upload_id) == b"real"


class TestEviction:
    async def test_expired_session_is_cleaned_up(self, tmp_path: Path) -> None:
        store = UploadStore(base=tmp_path / "chunked-uploads")
        async with store.lifespan():
            upload_id = store.create(MAX_BYTES, owner=OWNER)
            await store.write_chunk_stream(upload_id, 0, _one(b"data"))

            store._evict(upload_id)

            with pytest.raises(KeyError):
                store.assemble(upload_id, owner=OWNER)

    async def test_eviction_during_write_surfaces_as_key_error(
        self, store: UploadStore
    ) -> None:
        upload_id = store.create(MAX_BYTES, owner=OWNER)
        session_dir = store._upload_dir(upload_id)

        async def gen() -> AsyncIterator[bytes]:
            shutil.rmtree(session_dir)
            yield b"doomed"

        with pytest.raises(KeyError):
            await store.write_chunk_stream(upload_id, 0, gen())
