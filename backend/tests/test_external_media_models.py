from datetime import UTC, datetime, timedelta

from app.models.album_media import (
    AlbumMedia,
    AlbumMediaUndoSnapshot,
    StepPageMedia,
    StepUnusedMedia,
)


def test_album_media_keeps_name_as_identity() -> None:
    media = AlbumMedia(
        uid=1,
        aid="trip-1",
        name="11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg",
        kind="photo",
        width=1600,
        height=1200,
        byte_size=123456,
        upgrade_candidate=True,
    )

    dumped = media.model_dump()
    assert dumped["name"] == media.name
    assert media.kind == "photo"
    assert media.upgrade_candidate is True
    assert "storage_path" not in dumped
    assert "source_ref_id" not in dumped


def test_step_page_media_uses_position_as_identity() -> None:
    placement = StepPageMedia(
        uid=1,
        aid="trip-1",
        step_id=7,
        media_name="11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg",
        page_index=2,
        position_index=3,
    )

    dumped = placement.model_dump()
    assert "id" not in dumped
    assert placement.page_index == 2
    assert placement.position_index == 3


def test_step_unused_media_uses_position_as_identity() -> None:
    placement = StepUnusedMedia(
        uid=1,
        aid="trip-1",
        step_id=7,
        media_name="11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg",
        position_index=0,
    )

    dumped = placement.model_dump()
    assert "id" not in dumped
    assert placement.position_index == 0


def test_undo_snapshot_expires_after_five_minutes() -> None:
    now = datetime.now(UTC)
    snap = AlbumMediaUndoSnapshot(
        uid=1,
        aid="trip-1",
        media_name="11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg",
        snapshot_path=".undo/11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg",
        upgrade_candidate=True,
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )

    assert snap.expires_at - snap.created_at == timedelta(minutes=5)
