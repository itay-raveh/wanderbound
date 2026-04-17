"""Unit tests for the UploadStore chunked-upload manager."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.logic.chunked_upload import UploadStore

MAX_BYTES = 1024 * 1024  # 1 MiB - small limit for tests


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[UploadStore]:
    store = UploadStore(base=tmp_path / "chunked-uploads")
    async with store.lifespan():
        yield store


class TestWriteChunk:
    async def test_rejects_negative_index(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        with pytest.raises(ValueError, match="out of range"):
            store.write_chunk(upload_id, -1, b"x")

    async def test_rejects_index_above_9999(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        with pytest.raises(ValueError, match="out of range"):
            store.write_chunk(upload_id, 10_000, b"x")

    async def test_rejects_oversized_chunk(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        huge = b"\x00" * (80 * 1024 * 1024 + 2048)  # exceeds _CHUNK_LIMIT
        with pytest.raises(ValueError, match="limit"):
            store.write_chunk(upload_id, 0, huge)

    async def test_rejects_accumulated_overflow(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        store.write_chunk(upload_id, 0, b"\x00" * (MAX_BYTES - 10))
        with pytest.raises(OverflowError):
            store.write_chunk(upload_id, 1, b"\x00" * 20)

    async def test_rejects_too_many_chunks(self, store: UploadStore) -> None:
        # max_chunks = MAX_BYTES // _CHUNK_LIMIT + 2 = 0 + 2 = 2 for 1 MiB
        upload_id = store.create(MAX_BYTES, owner="test")
        store.write_chunk(upload_id, 0, b"a")
        store.write_chunk(upload_id, 1, b"b")
        with pytest.raises(ValueError, match="Too many chunks"):
            store.write_chunk(upload_id, 2, b"c")

    async def test_retry_not_falsely_rejected_by_overflow(
        self, store: UploadStore
    ) -> None:
        """Retrying a chunk should deduct old size before the overflow check."""
        upload_id = store.create(100, owner="test")
        store.write_chunk(upload_id, 0, b"\x00" * 90)
        # Retry with a smaller chunk - effective total = 11, well under 100
        store.write_chunk(upload_id, 0, b"\x00" * 11)

    async def test_idempotent_retry_adjusts_size(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        store.write_chunk(upload_id, 0, b"hello")
        # Re-upload same index with different data - should succeed and
        # correct the accumulated size (not double-count).
        store.write_chunk(upload_id, 0, b"world!")
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
        store.write_chunk(upload_id, 0, b"a")
        store.write_chunk(upload_id, 0, b"a")  # retry - should not increment count
        store.write_chunk(upload_id, 1, b"b")  # second distinct chunk - should work

    async def test_unknown_session_raises_key_error(self, store: UploadStore) -> None:
        with pytest.raises(KeyError):
            store.write_chunk("nonexistent", 0, b"x")


class TestAssemble:
    async def test_chunks_concatenated_in_order(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        store.write_chunk(upload_id, 1, b"BBB")
        store.write_chunk(upload_id, 0, b"AAA")

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
        store.write_chunk(upload_id, 0, b"x")
        assembled, _ = store.assemble(upload_id, owner="test")
        assembled.close()
        # Second assemble should fail - session was consumed
        with pytest.raises(KeyError):
            store.assemble(upload_id, owner="test")

    async def test_wrong_owner_raises_permission_error(
        self, store: UploadStore
    ) -> None:
        upload_id = store.create(MAX_BYTES, owner="alice")
        store.write_chunk(upload_id, 0, b"x")
        with pytest.raises(PermissionError, match="different user"):
            store.assemble(upload_id, owner="bob")

    async def test_non_contiguous_chunks_raises(self, store: UploadStore) -> None:
        upload_id = store.create(MAX_BYTES, owner="test")
        store.write_chunk(upload_id, 0, b"AAA")
        store.write_chunk(upload_id, 2, b"CCC")  # skipped index 1
        with pytest.raises(ValueError, match="not contiguous"):
            store.assemble(upload_id, owner="test")

    async def test_assemble_ignores_orphan_part_files(self, store: UploadStore) -> None:
        """Orphan .part tempfiles from crashed streaming writes are ignored."""
        upload_id = store.create(MAX_BYTES, owner="test")
        store.write_chunk(upload_id, 0, b"real")
        # Simulate a stale tempfile from a crashed mid-commit streaming write
        session = store._sessions[upload_id]
        (session.dir / f"0000.{'ab' * 8}.part").write_bytes(b"STALE")

        assembled, _ = store.assemble(upload_id, owner="test")
        try:
            assert assembled.read() == b"real"
        finally:
            assembled.close()


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

    async def test_stream_rejects_accumulated_overflow(
        self, store: UploadStore
    ) -> None:
        upload_id = store.create(100, owner="test")

        async def gen_big() -> AsyncIterator[bytes]:
            yield b"\x00" * 90

        await store.write_chunk_stream(upload_id, 0, gen_big())

        async def gen_overflow() -> AsyncIterator[bytes]:
            yield b"\x00" * 20

        with pytest.raises(OverflowError):
            await store.write_chunk_stream(upload_id, 1, gen_overflow())


class TestEviction:
    async def test_expired_session_is_cleaned_up(self, tmp_path: Path) -> None:
        store = UploadStore(base=tmp_path / "chunked-uploads")
        async with store.lifespan():
            upload_id = store.create(MAX_BYTES, owner="test")
            store.write_chunk(upload_id, 0, b"data")

            store._evict(upload_id)

            with pytest.raises(KeyError):
                store.assemble(upload_id, owner="test")
