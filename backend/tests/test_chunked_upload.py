"""Unit tests for the UploadStore chunked-upload manager."""

import asyncio
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.logic.chunked_upload import UploadStore

MAX_BYTES = 1024 * 1024  # 1 MiB - small limit for tests


async def _one(data: bytes) -> AsyncIterator[bytes]:
    yield data


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[UploadStore]:
    store = UploadStore(base=tmp_path / "chunked-uploads")
    async with store.lifespan():
        yield store


class TestWriteChunkStream:
    async def test_writes_stream_to_disk(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")

        async def gen() -> AsyncIterator[bytes]:
            yield b"hello "
            yield b"world"

        await store.write_chunk_stream(upload_id, 0, gen())
        assembled, _ = store.assemble(upload_id, owner="test")
        try:
            assert assembled.read() == b"hello world"
        finally:
            assembled.close()

    async def test_rejects_negative_index(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        with pytest.raises(ValueError, match="out of range"):
            await store.write_chunk_stream(upload_id, -1, _one(b"x"))

    async def test_rejects_index_above_9999(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        with pytest.raises(ValueError, match="out of range"):
            await store.write_chunk_stream(upload_id, 10_000, _one(b"x"))

    async def test_rejects_chunk_exceeding_limit_mid_stream(
        self, store: UploadStore
    ) -> None:
        """A chunk that grows past _CHUNK_LIMIT mid-stream is aborted."""
        upload_id = store.create(MAX_BYTES, owner="test")

        # _CHUNK_LIMIT is 80 MiB + 1 KiB. Stream 81 MiB in 1 MiB pieces.
        async def gen() -> AsyncIterator[bytes]:
            for _ in range(81):
                yield b"\x00" * (1024 * 1024)

        with pytest.raises(ValueError, match="exceeds"):
            await store.write_chunk_stream(upload_id, 0, gen())

    async def test_tempfile_cleaned_up_on_error(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")

        async def gen() -> AsyncIterator[bytes]:
            for _ in range(81):
                yield b"\x00" * (1024 * 1024)

        with pytest.raises(ValueError, match="exceeds"):
            await store.write_chunk_stream(upload_id, 0, gen())

        # No .part files should remain in the session directory
        session_dir = store._sessions[upload_id].dir
        leftover = list(session_dir.glob("*.part"))
        assert leftover == []

    async def test_rejects_accumulated_overflow(self, store: UploadStore) -> None:
        upload_id = store.create(100, owner="test")
        await store.write_chunk_stream(upload_id, 0, _one(b"\x00" * 90))

        with pytest.raises(OverflowError):
            await store.write_chunk_stream(upload_id, 1, _one(b"\x00" * 20))

    async def test_rejects_too_many_chunks(self, store: UploadStore) -> None:
        # max_chunks = MAX_BYTES // _CHUNK_LIMIT + 2 = 0 + 2 = 2 for 1 MiB
        upload_id = store.create(MAX_BYTES, owner="test")
        await store.write_chunk_stream(upload_id, 0, _one(b"a"))
        await store.write_chunk_stream(upload_id, 1, _one(b"b"))
        with pytest.raises(ValueError, match="Too many chunks"):
            await store.write_chunk_stream(upload_id, 2, _one(b"c"))

    async def test_retry_not_falsely_rejected_by_overflow(
        self, store: UploadStore
    ) -> None:
        """Retrying a chunk should deduct old size before the overflow check."""
        upload_id = store.create(100, owner="test")
        await store.write_chunk_stream(upload_id, 0, _one(b"\x00" * 90))
        # Retry with a smaller chunk - effective total = 11, well under 100
        await store.write_chunk_stream(upload_id, 0, _one(b"\x00" * 11))

    async def test_idempotent_retry_adjusts_size(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        await store.write_chunk_stream(upload_id, 0, _one(b"hello"))
        # Re-upload same index with different data - should succeed and
        # correct the accumulated size (not double-count).
        await store.write_chunk_stream(upload_id, 0, _one(b"world!"))
        assembled, _ = store.assemble(upload_id, owner="test")
        try:
            assert assembled.read() == b"world!"
        finally:
            assembled.close()

    async def test_idempotent_retry_does_not_count_toward_chunk_limit(
        self, store: UploadStore
    ) -> None:
        # max_chunks = 2 for 1 MiB limit
        upload_id = store.create(MAX_BYTES, owner="test")
        await store.write_chunk_stream(upload_id, 0, _one(b"a"))
        await store.write_chunk_stream(upload_id, 0, _one(b"a"))  # retry
        await store.write_chunk_stream(upload_id, 1, _one(b"b"))  # distinct chunk

    async def test_unknown_session_raises_key_error(self, store: UploadStore) -> None:
        with pytest.raises(KeyError):
            await store.write_chunk_stream("nonexistent", 0, _one(b"x"))

    async def test_concurrent_same_index_writes_do_not_corrupt(
        self, store: UploadStore
    ) -> None:
        """Two concurrent writes for the same chunk index must not corrupt."""
        upload_id = store.create(MAX_BYTES, owner="test")

        async def gen_a() -> AsyncIterator[bytes]:
            yield b"AAAA"

        async def gen_b() -> AsyncIterator[bytes]:
            yield b"BBBB"

        # Both writes target index 0 - whichever renames last wins, but
        # neither should produce garbage bytes in the final chunk.
        await asyncio.gather(
            store.write_chunk_stream(upload_id, 0, gen_a()),
            store.write_chunk_stream(upload_id, 0, gen_b()),
        )

        assembled, _ = store.assemble(upload_id, owner="test")
        try:
            final = assembled.read()
            assert final in (b"AAAA", b"BBBB")
        finally:
            assembled.close()

    async def test_concurrent_different_index_writes(self, store: UploadStore) -> None:
        """Concurrent writes to different indices produce the union."""
        upload_id = store.create(MAX_BYTES, owner="test")

        async def gen(payload: bytes) -> AsyncIterator[bytes]:
            yield payload

        await asyncio.gather(
            store.write_chunk_stream(upload_id, 0, gen(b"AAA")),
            store.write_chunk_stream(upload_id, 1, gen(b"BBB")),
            store.write_chunk_stream(upload_id, 2, gen(b"CCC")),
        )

        assembled, _ = store.assemble(upload_id, owner="test")
        try:
            assert assembled.read() == b"AAABBBCCC"
        finally:
            assembled.close()


class TestAssemble:
    async def test_chunks_concatenated_in_order(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        await store.write_chunk_stream(upload_id, 1, _one(b"BBB"))
        await store.write_chunk_stream(upload_id, 0, _one(b"AAA"))

        assembled, _ = store.assemble(upload_id, owner="test")
        try:
            assert assembled.read() == b"AAABBB"
        finally:
            assembled.close()

    async def test_no_chunks_raises(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        with pytest.raises(ValueError, match="No chunks"):
            store.assemble(upload_id, owner="test")

    async def test_unknown_session_raises_key_error(self, store: UploadStore) -> None:
        with pytest.raises(KeyError):
            store.assemble("nonexistent", owner="test")

    async def test_session_removed_after_assemble(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        await store.write_chunk_stream(upload_id, 0, _one(b"x"))
        assembled, _ = store.assemble(upload_id, owner="test")
        assembled.close()
        # Second assemble should fail - session was consumed
        with pytest.raises(KeyError):
            store.assemble(upload_id, owner="test")

    async def test_wrong_owner_raises_permission_error(
        self, store: UploadStore
    ) -> None:
        upload_id = store.create(MAX_BYTES, owner="alice")
        await store.write_chunk_stream(upload_id, 0, _one(b"x"))
        with pytest.raises(PermissionError, match="different user"):
            store.assemble(upload_id, owner="bob")

    async def test_non_contiguous_chunks_raises(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        await store.write_chunk_stream(upload_id, 0, _one(b"AAA"))
        await store.write_chunk_stream(upload_id, 2, _one(b"CCC"))  # skipped index 1
        with pytest.raises(ValueError, match="not contiguous"):
            store.assemble(upload_id, owner="test")

    async def test_assemble_ignores_orphan_part_files(self, store: UploadStore) -> None:
        """Orphan .part tempfiles from crashed streaming writes are ignored."""
        upload_id = store.create(MAX_BYTES, owner="test")
        await store.write_chunk_stream(upload_id, 0, _one(b"real"))
        # Simulate a stale tempfile from a crashed mid-commit streaming write
        session = store._sessions[upload_id]
        (session.dir / f"0000.{'ab' * 8}.part").write_bytes(b"STALE")

        assembled, _ = store.assemble(upload_id, owner="test")
        try:
            assert assembled.read() == b"real"
        finally:
            assembled.close()


class TestEviction:
    async def test_expired_session_is_cleaned_up(self, tmp_path: Path) -> None:
        store = UploadStore(base=tmp_path / "chunked-uploads")
        async with store.lifespan():
            upload_id = store.create(MAX_BYTES, owner="test")
            await store.write_chunk_stream(upload_id, 0, _one(b"data"))

            store._evict(upload_id)

            with pytest.raises(KeyError):
                store.assemble(upload_id, owner="test")

    async def test_eviction_during_write_surfaces_as_key_error(
        self, store: UploadStore
    ) -> None:
        """A write already in flight when eviction runs raises KeyError, not OSError."""
        upload_id = store.create(MAX_BYTES, owner="test")
        session = store._sessions[upload_id]

        async def gen() -> AsyncIterator[bytes]:
            # Simulate TTL eviction firing after the session lookup but before
            # the write completes: dir gone, session popped from registry.
            shutil.rmtree(session.dir)
            store._sessions.pop(upload_id)
            session.timer.cancel()
            yield b"doomed"

        with pytest.raises(KeyError):
            await store.write_chunk_stream(upload_id, 0, gen())
