from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from app.logic.workflows.media_hashes import (
    HashBackfillStats,
    discover_missing_media_hashes,
    enqueue_media_hash_backfill,
    hash_media_batch,
    media_hash_backfill_revision,
    media_hash_backfill_workflow,
    media_hash_workflow_id,
    missing_media_hash_backfill_targets,
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
    from sqlmodel.ext.asyncio.session import AsyncSession


def test_media_hash_workflow_id_is_scoped_to_missing_hash_revision() -> None:
    assert media_hash_workflow_id(42, "trip-1", 7, "abc123") == (
        "media-hash-backfill:42:trip-1:7:abc123"
    )


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

    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.SetWorkflowID", FakeSetWorkflowID
    )
    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.DBOS.enqueue_workflow_async", fake_enqueue
    )
    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.DBOS.get_workflow_status_async",
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


async def _async_value(value: object) -> object:
    return value


async def test_enqueue_forks_one_retry_for_a_terminally_errored_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = type("Status", (), {"status": "ERROR"})()
    handle = object()
    workflow_ids: list[str] = []

    class FakeSetWorkflowID:
        def __init__(self, workflow_id: str) -> None:
            self.workflow_id = workflow_id

        def __enter__(self) -> None:
            workflow_ids.append(self.workflow_id)

        def __exit__(self, *_args: object) -> None:
            return None

    async def get_status(workflow_id: str) -> object | None:
        return status if not workflow_id.endswith(":retry:1") else None

    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.DBOS.get_workflow_status_async",
        get_status,
    )
    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.SetWorkflowID", FakeSetWorkflowID
    )

    async def fork(workflow_id: str, start_step: int, *, queue_name: str) -> object:
        assert workflow_id == "media-hash-backfill:42:trip-1:7:abc123"
        assert start_step == 0
        assert queue_name == "media-hash-backfill"
        return handle

    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.DBOS.fork_workflow_async", fork
    )
    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.DBOS.enqueue_workflow_async",
        lambda *_args: pytest.fail("errored workflow should be forked"),
    )

    result = await enqueue_media_hash_backfill(42, "trip-1", 7, "abc123")

    assert result is handle
    assert workflow_ids == ["media-hash-backfill:42:trip-1:7:abc123:retry:1"]


async def test_enqueue_does_not_repeat_a_terminal_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_status = type("Status", (), {"status": "ERROR"})()
    retry_status = type("Status", (), {"status": "ERROR"})()

    async def get_status(workflow_id: str) -> object:
        return retry_status if workflow_id.endswith(":retry:1") else original_status

    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.DBOS.get_workflow_status_async",
        get_status,
    )
    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.DBOS.fork_workflow_async",
        lambda *_args, **_kwargs: pytest.fail("retry must remain bounded"),
    )

    result = await enqueue_media_hash_backfill(42, "trip-1", 7, "abc123")

    assert result is retry_status


async def test_missing_targets_use_latest_successful_generation_or_legacy_zero(
    session: AsyncSession,
) -> None:
    await insert_album(session, 1, "trip-1")
    await insert_album_media(session, 1, "trip-1")
    await insert_album(session, 1, "trip-2")
    await insert_album_media(session, 1, "trip-2", name=MISSING_MEDIA_NAME)
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

    actual = [(target.uid, target.aid, target.upload_generation) for target in targets]
    assert actual == [
        (1, "trip-1", 3),
        (1, "trip-2", 3),
        (2, "legacy-trip", 0),
    ]
    assert all(target.revision for target in targets)


async def test_missing_hash_revision_changes_after_hash_invalidation(
    session: AsyncSession,
) -> None:
    await insert_album(session, 1, "trip-1")
    media = await insert_album_media(session, 1, "trip-1")
    await session.commit()
    before = await media_hash_backfill_revision(session, 1, "trip-1")

    media.updated_at = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    session.add(media)
    await session.commit()
    after = await media_hash_backfill_revision(session, 1, "trip-1")

    assert before is not None
    assert after is not None
    assert after != before


async def test_revision_stays_stable_while_a_backfill_makes_progress(
    session: AsyncSession,
) -> None:
    await insert_album(session, 1, "trip-1")
    first = await insert_album_media(session, 1, "trip-1")
    await insert_album_media(session, 1, "trip-1", name=MISSING_MEDIA_NAME)
    await session.commit()
    before = await media_hash_backfill_revision(session, 1, "trip-1")

    first.perceptual_hashes = ["0123456789abcdef"]
    session.add(first)
    await session.commit()
    after = await media_hash_backfill_revision(session, 1, "trip-1")

    assert before is not None
    assert after == before


async def _missing_media(
    session: AsyncSession,
    album_dir: Path,
    *,
    name: str = DEFAULT_MEDIA_NAME,
) -> AlbumMedia:
    media = await insert_album_media(session, 1, name=name)
    path = create_test_jpeg(album_dir / name, 800, 600)
    media.byte_size = path.stat().st_size
    session.add(media)
    await session.commit()
    return media


async def test_discovers_a_finite_snapshot_of_missing_existing_media(
    session: AsyncSession, tmp_path: Path
) -> None:
    await insert_album(session, 1)
    missing = await _missing_media(session, tmp_path)
    prefilled = await insert_album_media(session, 1, name=MISSING_MEDIA_NAME)
    prefilled.perceptual_hashes = ["0123456789abcdef"]
    absent = await insert_album_media(session, 1, name="absent.jpg")
    session.add_all([prefilled, absent])
    await session.commit()

    discovery = await discover_missing_media_hashes(session, 1, "trip-1", tmp_path)

    assert [candidate.name for candidate in discovery.candidates] == [missing.name]
    assert discovery.excluded == 1
    assert discovery.candidates[0].file.size == missing.byte_size


async def test_hash_batch_persists_current_media(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await insert_album(session, 1)
    media = await _missing_media(session, tmp_path)
    discovery = await discover_missing_media_hashes(session, 1, "trip-1", tmp_path)
    cache = object()
    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.local_hash_cache",
        lambda _album_dir: cache,
    )

    def hash_with_cache(
        _paths: object, *, workers: int, cached_hash: object
    ) -> dict[str, list[str]]:
        assert cached_hash is cache
        return {media.name: ["0123456789abcdef"]}

    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.compute_serialized_media_hashes",
        hash_with_cache,
    )

    result = await hash_media_batch(session, tmp_path, discovery.candidates)

    await session.refresh(media)
    assert result == HashBackfillStats(hashed=1)
    assert media.perceptual_hashes == ["0123456789abcdef"]


async def test_hash_batch_does_not_overwrite_a_hash_filled_concurrently(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await insert_album(session, 1)
    media = await _missing_media(session, tmp_path)
    discovery = await discover_missing_media_hashes(session, 1, "trip-1", tmp_path)
    media.perceptual_hashes = ["fedcba9876543210"]
    session.add(media)
    await session.commit()
    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.compute_serialized_media_hashes",
        lambda _paths, **_kwargs: {media.name: ["0123456789abcdef"]},
    )

    result = await hash_media_batch(session, tmp_path, discovery.candidates)

    await session.refresh(media)
    assert result == HashBackfillStats(already_completed=1)
    assert media.perceptual_hashes == ["fedcba9876543210"]


async def test_hash_batch_rejects_a_changed_database_row(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await insert_album(session, 1)
    media = await _missing_media(session, tmp_path)
    discovery = await discover_missing_media_hashes(session, 1, "trip-1", tmp_path)
    media.byte_size += 1
    media.updated_at = datetime.now(UTC)
    session.add(media)
    await session.commit()
    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.compute_serialized_media_hashes",
        lambda _paths, **_kwargs: {media.name: ["0123456789abcdef"]},
    )

    result = await hash_media_batch(session, tmp_path, discovery.candidates)

    await session.refresh(media)
    assert result == HashBackfillStats(stale=1)
    assert media.perceptual_hashes is None


async def test_hash_batch_rejects_a_replaced_file(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await insert_album(session, 1)
    media = await _missing_media(session, tmp_path)
    discovery = await discover_missing_media_hashes(session, 1, "trip-1", tmp_path)
    assert len(discovery.candidates) == 1
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 800, 600)
    replacement.replace(tmp_path / media.name)
    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.compute_serialized_media_hashes",
        lambda _paths, **_kwargs: {media.name: ["0123456789abcdef"]},
    )

    result = await hash_media_batch(session, tmp_path, discovery.candidates)

    await session.refresh(media)
    assert result == HashBackfillStats(stale=1)
    assert media.perceptual_hashes is None


async def test_hash_failure_finishes_the_finite_batch(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await insert_album(session, 1)
    await _missing_media(session, tmp_path)
    revision = await media_hash_backfill_revision(session, 1, "trip-1")
    discovery = await discover_missing_media_hashes(session, 1, "trip-1", tmp_path)
    calls = 0

    def fail_hashes(_paths: object, **_kwargs: object) -> dict[str, list[str]]:
        nonlocal calls
        calls += 1
        return {}

    monkeypatch.setattr(
        "app.logic.workflows.media_hashes.compute_serialized_media_hashes",
        fail_hashes,
    )

    result = await hash_media_batch(session, tmp_path, discovery.candidates)

    assert result == HashBackfillStats(failed=1)
    assert calls == 1
    assert await media_hash_backfill_revision(session, 1, "trip-1") == revision
