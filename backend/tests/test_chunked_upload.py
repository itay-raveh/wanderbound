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
        uid = store.create(MAX_BYTES, owner="test")
        with pytest.raises(ValueError, match="out of range"):
            store.write_chunk(uid, -1, b"x")

    async def test_rejects_index_above_9999(self, store: UploadStore) -> None:
        uid = store.create(MAX_BYTES, owner="test")
        with pytest.raises(ValueError, match="out of range"):
            store.write_chunk(uid, 10_000, b"x")

    async def test_rejects_oversized_chunk(self, store: UploadStore) -> None:
        uid = store.create(MAX_BYTES, owner="test")
        huge = b"\x00" * (80 * 1024 * 1024 + 2048)  # exceeds _CHUNK_LIMIT
        with pytest.raises(ValueError, match="limit"):
            store.write_chunk(uid, 0, huge)

    async def test_rejects_accumulated_overflow(self, store: UploadStore) -> None:
        uid = store.create(MAX_BYTES, owner="test")
        store.write_chunk(uid, 0, b"\x00" * (MAX_BYTES - 10))
        with pytest.raises(OverflowError):
            store.write_chunk(uid, 1, b"\x00" * 20)

    async def test_rejects_too_many_chunks(self, store: UploadStore) -> None:
        # max_chunks = MAX_BYTES // _CHUNK_LIMIT + 2 = 0 + 2 = 2 for 1 MiB
        uid = store.create(MAX_BYTES, owner="test")
        store.write_chunk(uid, 0, b"a")
        store.write_chunk(uid, 1, b"b")
        with pytest.raises(ValueError, match="Too many chunks"):
            store.write_chunk(uid, 2, b"c")

    async def test_retry_not_falsely_rejected_by_overflow(
        self, store: UploadStore
    ) -> None:
        """Retrying a chunk should deduct old size before the overflow check."""
        uid = store.create(100, owner="test")
        store.write_chunk(uid, 0, b"\x00" * 90)
        # Retry with a smaller chunk - effective total = 11, well under 100
        store.write_chunk(uid, 0, b"\x00" * 11)

    async def test_idempotent_retry_adjusts_size(self, store: UploadStore) -> None:
        uid = store.create(MAX_BYTES, owner="test")
        store.write_chunk(uid, 0, b"hello")
        # Re-upload same index with different data - should succeed and
        # correct the accumulated size (not double-count).
        store.write_chunk(uid, 0, b"world!")
        assembled, _ = store.assemble(uid, owner="test")
        try:
            assert assembled.read() == b"world!"
        finally:
            assembled.close()

    async def test_idempotent_retry_does_not_count_toward_chunk_limit(
        self, store: UploadStore
    ) -> None:
        # max_chunks = 2 for 1 MiB limit
        uid = store.create(MAX_BYTES, owner="test")
        store.write_chunk(uid, 0, b"a")
        store.write_chunk(uid, 0, b"a")  # retry - should not increment count
        store.write_chunk(uid, 1, b"b")  # second distinct chunk - should work

    async def test_unknown_session_raises_key_error(self, store: UploadStore) -> None:
        with pytest.raises(KeyError):
            store.write_chunk("nonexistent", 0, b"x")


class TestAssemble:
    async def test_chunks_concatenated_in_order(self, store: UploadStore) -> None:
        uid = store.create(MAX_BYTES, owner="test")
        store.write_chunk(uid, 1, b"BBB")
        store.write_chunk(uid, 0, b"AAA")

        assembled, _ = store.assemble(uid, owner="test")
        try:
            assert assembled.read() == b"AAABBB"
        finally:
            assembled.close()

    async def test_no_chunks_raises(self, store: UploadStore) -> None:
        uid = store.create(MAX_BYTES, owner="test")
        with pytest.raises(ValueError, match="No chunks"):
            store.assemble(uid, owner="test")

    async def test_unknown_session_raises_key_error(self, store: UploadStore) -> None:
        with pytest.raises(KeyError):
            store.assemble("nonexistent", owner="test")

    async def test_session_removed_after_assemble(self, store: UploadStore) -> None:
        uid = store.create(MAX_BYTES, owner="test")
        store.write_chunk(uid, 0, b"x")
        assembled, _ = store.assemble(uid, owner="test")
        assembled.close()
        # Second assemble should fail - session was consumed
        with pytest.raises(KeyError):
            store.assemble(uid, owner="test")

    async def test_wrong_owner_raises_permission_error(
        self, store: UploadStore
    ) -> None:
        uid = store.create(MAX_BYTES, owner="alice")
        store.write_chunk(uid, 0, b"x")
        with pytest.raises(PermissionError, match="different user"):
            store.assemble(uid, owner="bob")

    async def test_non_contiguous_chunks_raises(self, store: UploadStore) -> None:
        uid = store.create(MAX_BYTES, owner="test")
        store.write_chunk(uid, 0, b"AAA")
        store.write_chunk(uid, 2, b"CCC")  # skipped index 1
        with pytest.raises(ValueError, match="not contiguous"):
            store.assemble(uid, owner="test")


class TestEviction:
    async def test_expired_session_is_cleaned_up(self, tmp_path: Path) -> None:
        store = UploadStore(base=tmp_path / "chunked-uploads")
        async with store.lifespan():
            uid = store.create(MAX_BYTES, owner="test")
            store.write_chunk(uid, 0, b"data")

            store._evict(uid)

            with pytest.raises(KeyError):
                store.assemble(uid, owner="test")
