from datetime import UTC, datetime, timedelta

from app.models.album_media import (
    AlbumMedia,
    AlbumMediaSourceKind,
    AlbumMediaSourceRef,
    AlbumMediaUndoSnapshot,
)


def test_album_media_keeps_name_as_identity() -> None:
    media = AlbumMedia(
        uid=1,
        aid="trip-1",
        name="11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg",
        kind="photo",
        storage_path="11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg",
        width=1600,
        height=1200,
        byte_size=123456,
        source_ref_id=None,
    )

    assert media.name == media.storage_path
    assert media.kind == "photo"


def test_source_ref_does_not_require_url_or_filename() -> None:
    ref = AlbumMediaSourceRef(
        uid=1,
        aid="trip-1",
        source_kind=AlbumMediaSourceKind.google_photos,
        google_media_id="google-id-1",
        mime_type="image/jpeg",
        width=4000,
        height=3000,
        captured_at=None,
    )

    dumped = ref.model_dump()
    assert "base_url" not in dumped
    assert "filename" not in dumped


def test_undo_snapshot_expires_after_five_minutes() -> None:
    now = datetime.now(UTC)
    snap = AlbumMediaUndoSnapshot(
        uid=1,
        aid="trip-1",
        media_name="11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg",
        snapshot_path=".undo/11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )

    assert snap.expires_at - snap.created_at == timedelta(minutes=5)
