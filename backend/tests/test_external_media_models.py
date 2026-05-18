from datetime import timedelta

from tests.factories import (
    DEFAULT_MEDIA_NAME,
    make_album_media,
    make_step_page_media,
    make_step_unused_media,
    make_undo_snapshot,
)


def test_album_media_keeps_name_as_identity() -> None:
    media = make_album_media(
        name=DEFAULT_MEDIA_NAME,
        width=1600,
        height=1200,
        byte_size=123456,
    )

    dumped = media.model_dump()
    assert dumped["name"] == media.name
    assert media.kind == "photo"
    assert media.upgrade_candidate is True
    assert "storage_path" not in dumped
    assert "source_ref_id" not in dumped


def test_step_page_media_uses_position_as_identity() -> None:
    placement = make_step_page_media(
        step_id=7,
        media_name=DEFAULT_MEDIA_NAME,
        page_index=2,
        position_index=3,
    )

    dumped = placement.model_dump()
    assert "id" not in dumped
    assert placement.page_index == 2
    assert placement.position_index == 3


def test_step_unused_media_uses_position_as_identity() -> None:
    placement = make_step_unused_media(
        step_id=7,
        media_name=DEFAULT_MEDIA_NAME,
        position_index=0,
    )

    dumped = placement.model_dump()
    assert "id" not in dumped
    assert placement.position_index == 0


def test_undo_snapshot_expires_after_five_minutes() -> None:
    snap = make_undo_snapshot()

    assert snap.expires_at - snap.created_at == timedelta(minutes=5)
