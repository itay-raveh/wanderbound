from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.logic.workflows import media_hashes
from app.logic.workflows.media_hashes import (
    HashBackfillStats,
    MediaHashCandidate,
    MediaHashWorkflowPayload,
    backfill_media_hashes,
    enqueue_media_hash_backfill,
    media_hash_backfill_revision,
    media_hash_backfill_workflow,
    media_hash_workflow_id,
    missing_media_hash_backfill_targets,
    persist_media_hash_batch,
)
from app.models.album_media import AlbumMedia
from app.models.processing import ProcessingOperation
from tests.factories import (
    DEFAULT_MEDIA_NAME,
    MISSING_MEDIA_NAME,
    create_test_jpeg,
    insert_album,
    insert_album_media,
)

if TYPE_CHECKING:
    from types import TracebackType

    from sqlmodel.ext.asyncio.session import AsyncSession


async def test_workflow_delegates_to_one_album_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {"hashed": 3, "already_completed": 0, "stale": 0, "failed": 0}

    async def backfill(payload: dict[str, object]) -> dict[str, int]:
        assert payload == {"uid": 42, "aid": "trip-1"}
        return expected

    monkeypatch.setattr(media_hashes, "backfill_media_hashes_step", backfill)

    result = await media_hash_backfill_workflow.__wrapped__.__wrapped__(
        {"uid": 42, "aid": "trip-1"}
    )

    assert result == expected


def test_media_hash_workflow_id_is_scoped_to_missing_hash_revision() -> None:
    assert media_hash_workflow_id(42, "trip-1", 7, "abc123") == (
        "media-hash-backfill:42:trip-1:7:abc123"
    )


async def _async_value(value: object) -> object:
    return value


async def test_enqueue_uses_the_deterministic_workflow_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_ids: list[str] = []
    calls: list[tuple[str, object, dict[str, object]]] = []
    handle = object()

    class FakeSetWorkflowID:
        def __init__(self, workflow_id: str) -> None:
            self.workflow_id = workflow_id

        def __enter__(self) -> None:
            workflow_ids.append(self.workflow_id)

        def __exit__(self, *_args: object) -> None:
            return None

    async def fake_enqueue(
        queue_name: str, workflow: object, payload: dict[str, object]
    ) -> object:
        calls.append((queue_name, workflow, payload))
        return handle

    monkeypatch.setattr(media_hashes, "SetWorkflowID", FakeSetWorkflowID)
    monkeypatch.setattr(media_hashes.DBOS, "enqueue_workflow_async", fake_enqueue)
    monkeypatch.setattr(
        media_hashes.DBOS,
        "get_workflow_status_async",
        lambda _workflow_id: _async_value(None),
    )

    result = await enqueue_media_hash_backfill(42, "trip-1", 7, "abc123")

    assert result is handle
    assert workflow_ids == ["media-hash-backfill:42:trip-1:7:abc123"]
    assert calls == [
        (
            "media-hash-backfill",
            media_hash_backfill_workflow,
            {"uid": 42, "aid": "trip-1"},
        )
    ]


async def test_enqueue_retries_a_terminal_revision_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_status = type("Status", (), {"status": "ERROR"})()
    retry_status = type("Status", (), {"status": "ERROR"})()
    forked = object()
    workflow_ids: list[str] = []

    class FakeSetWorkflowID:
        def __init__(self, workflow_id: str) -> None:
            self.workflow_id = workflow_id

        def __enter__(self) -> None:
            workflow_ids.append(self.workflow_id)

        def __exit__(self, *_args: object) -> None:
            return None

    async def get_status(workflow_id: str) -> object | None:
        if workflow_id.endswith(":retry:1"):
            return None
        return original_status

    async def fork(workflow_id: str, start_step: int, *, queue_name: str) -> object:
        assert workflow_id == "media-hash-backfill:42:trip-1:7:abc123"
        assert start_step == 0
        assert queue_name == "media-hash-backfill"
        return forked

    monkeypatch.setattr(media_hashes, "SetWorkflowID", FakeSetWorkflowID)
    monkeypatch.setattr(media_hashes.DBOS, "get_workflow_status_async", get_status)
    monkeypatch.setattr(media_hashes.DBOS, "fork_workflow_async", fork)

    assert await enqueue_media_hash_backfill(42, "trip-1", 7, "abc123") is forked
    assert workflow_ids == ["media-hash-backfill:42:trip-1:7:abc123:retry:1"]

    async def retry_exists(_workflow_id: str) -> object:
        return retry_status

    monkeypatch.setattr(media_hashes.DBOS, "get_workflow_status_async", retry_exists)
    assert await enqueue_media_hash_backfill(42, "trip-1", 7, "abc123") is retry_status


async def test_missing_targets_use_latest_successful_generation_and_ignore_videos(
    session: AsyncSession,
) -> None:
    await insert_album(session, 1, "trip-1")
    await insert_album_media(session, 1, "trip-1")
    await insert_album(session, 1, "video-trip")
    await insert_album_media(
        session,
        1,
        "video-trip",
        name=DEFAULT_MEDIA_NAME.replace(".jpg", ".mp4"),
    )
    await insert_album(session, 2, "legacy-trip")
    await insert_album_media(session, 2, "legacy-trip")
    session.add_all(
        [
            ProcessingOperation(
                uid=1,
                upload_generation=3,
                workflow_id="processing:3",
                status="succeeded",
            ),
            ProcessingOperation(
                uid=1,
                upload_generation=4,
                workflow_id="processing:4",
                status="failed",
            ),
        ]
    )
    await session.commit()

    targets = await missing_media_hash_backfill_targets(session)

    assert [
        (target.uid, target.aid, target.upload_generation) for target in targets
    ] == [(1, "trip-1", 3), (2, "legacy-trip", 0)]
    assert all(target.revision for target in targets)


async def test_revision_tracks_media_identity_but_not_hash_progress(
    session: AsyncSession,
) -> None:
    await insert_album(session, 1, "trip-1")
    first = await insert_album_media(session, 1, "trip-1")
    second = await insert_album_media(session, 1, "trip-1", name=MISSING_MEDIA_NAME)
    await session.commit()
    original = await media_hash_backfill_revision(session, 1, "trip-1")

    first.perceptual_hashes = ["0123456789abcdef"]
    session.add(first)
    await session.commit()
    assert await media_hash_backfill_revision(session, 1, "trip-1") == original

    second.updated_at = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    session.add(second)
    await session.commit()
    assert await media_hash_backfill_revision(session, 1, "trip-1") != original


async def _candidate(
    session: AsyncSession,
    album_dir: Path,
    *,
    name: str = DEFAULT_MEDIA_NAME,
) -> tuple[AlbumMedia, MediaHashCandidate]:
    media = await insert_album_media(session, 1, name=name)
    path = create_test_jpeg(album_dir / name, 800, 600)
    media.byte_size = path.stat().st_size
    session.add(media)
    await session.commit()
    return media, MediaHashCandidate(
        media.name,
        media.created_at,
        media.updated_at,
        media.byte_size,
        media_hashes._file_identity(path),
    )


async def test_persist_batch_updates_only_current_database_rows(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    await insert_album(session, 1)
    current, current_candidate = await _candidate(session, tmp_path)
    changed, changed_candidate = await _candidate(
        session, tmp_path, name=MISSING_MEDIA_NAME
    )
    changed.byte_size += 1
    changed.updated_at = datetime.now(UTC)
    session.add(changed)
    await session.commit()
    result = await persist_media_hash_batch(
        session,
        MediaHashWorkflowPayload(uid=1, aid="trip-1"),
        tmp_path,
        [current_candidate, changed_candidate],
        {
            current_candidate.name: ["0123456789abcdef"],
            changed_candidate.name: ["0123456789abcdef"],
        },
    )

    await session.refresh(current)
    await session.refresh(changed)
    assert result == HashBackfillStats(hashed=1, stale=1)
    assert current.perceptual_hashes == ["0123456789abcdef"]
    assert changed.perceptual_hashes is None


async def test_persist_batch_rejects_a_file_replaced_after_hashing(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    await insert_album(session, 1)
    media, candidate = await _candidate(session, tmp_path)

    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 800, 600)
    replacement.replace(tmp_path / candidate.name)

    result = await persist_media_hash_batch(
        session,
        MediaHashWorkflowPayload(uid=1, aid="trip-1"),
        tmp_path,
        [candidate],
        {candidate.name: ["0123456789abcdef"]},
    )

    await session.refresh(media)
    assert result == HashBackfillStats(stale=1)
    assert media.perceptual_hashes is None


async def test_persist_batch_preserves_a_concurrently_completed_hash(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    await insert_album(session, 1)
    media, candidate = await _candidate(session, tmp_path)
    media.perceptual_hashes = ["fedcba9876543210"]
    session.add(media)
    await session.commit()
    result = await persist_media_hash_batch(
        session,
        MediaHashWorkflowPayload(uid=1, aid="trip-1"),
        tmp_path,
        [candidate],
        {candidate.name: ["0123456789abcdef"]},
    )

    await session.refresh(media)
    assert result == HashBackfillStats(already_completed=1)
    assert media.perceptual_hashes == ["fedcba9876543210"]


class _SessionContext:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncSession:
        return self.session

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        return None


async def test_album_step_hashes_the_snapshot_once_before_committing_batches(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await insert_album(session, 1)
    _, first = await _candidate(session, tmp_path)
    _, second = await _candidate(session, tmp_path, name=MISSING_MEDIA_NAME)
    monkeypatch.setattr(media_hashes, "_HASH_BATCH_SIZE", 1)
    monkeypatch.setattr(
        media_hashes,
        "_discover_candidates",
        lambda *_args: _async_value(([first, second], 0)),
    )
    monkeypatch.setattr(
        media_hashes,
        "AsyncSession",
        lambda *_args, **_kwargs: _SessionContext(session),
    )
    calls = 0

    def hash_snapshot(paths: list[Path], **_kwargs: object) -> dict[str, list[str]]:
        nonlocal calls
        calls += 1
        return {path.name: ["0123456789abcdef"] for path in paths}

    monkeypatch.setattr(media_hashes, "compute_serialized_media_hashes", hash_snapshot)

    result = await backfill_media_hashes(1, "trip-1", tmp_path)

    assert result == HashBackfillStats(hashed=2)
    assert calls == 1


async def test_album_step_resumes_from_committed_batches(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await insert_album(session, 1)
    first, first_candidate = await _candidate(session, tmp_path)
    second, second_candidate = await _candidate(
        session, tmp_path, name=MISSING_MEDIA_NAME
    )
    candidates = [first_candidate, second_candidate]
    monkeypatch.setattr(media_hashes, "_HASH_BATCH_SIZE", 1)
    monkeypatch.setattr(
        media_hashes,
        "_discover_candidates",
        lambda *_args: _async_value((candidates, 0)),
    )
    monkeypatch.setattr(
        media_hashes,
        "AsyncSession",
        lambda *_args, **_kwargs: _SessionContext(session),
    )
    monkeypatch.setattr(
        media_hashes,
        "compute_serialized_media_hashes",
        lambda paths, **_kwargs: {path.name: ["0123456789abcdef"] for path in paths},
    )
    persist = persist_media_hash_batch
    attempts = 0

    async def interrupt_second_batch(*args: object, **kwargs: object) -> object:
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError("worker interrupted")
        return await persist(*args, **kwargs)

    monkeypatch.setattr(
        media_hashes,
        "persist_media_hash_batch",
        interrupt_second_batch,
    )

    with pytest.raises(RuntimeError, match="worker interrupted"):
        await backfill_media_hashes(1, "trip-1", tmp_path)

    await session.refresh(first)
    await session.refresh(second)
    assert first.perceptual_hashes == ["0123456789abcdef"]
    assert second.perceptual_hashes is None

    monkeypatch.setattr(media_hashes, "persist_media_hash_batch", persist)
    result = await backfill_media_hashes(1, "trip-1", tmp_path)

    await session.refresh(second)
    assert result == HashBackfillStats(hashed=1, already_completed=1)
    assert second.perceptual_hashes == ["0123456789abcdef"]
