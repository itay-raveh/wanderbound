from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks

from app.logic.external_media.album_media import replace_album_media_from_saved
from app.logic.external_media.undo import (
    enqueue_undo_snapshot_prune,
    restore_undo_snapshot,
    schedule_undo_snapshot_prune,
)
from app.logic.layout.media import Media
from app.logic.media_import import SavedInput
from app.models.album_media import AlbumMedia, AlbumMediaUndoSnapshot

from .factories import AID, create_test_jpeg, insert_album, insert_album_media

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


VALID_NAME = (
    "11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.jpg"
)
VALID_VIDEO_NAME = (
    "11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.mp4"
)
OLD_NAME = (
    "33333333-3333-4333-8333-333333333333_44444444-4444-4444-8444-444444444444.jpg"
)


def test_enqueue_undo_snapshot_prune_adds_scheduler_background_task(
    tmp_path: Path,
) -> None:
    background_tasks = BackgroundTasks()

    enqueue_undo_snapshot_prune(background_tasks, 123, "album-1", tmp_path)

    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is schedule_undo_snapshot_prune
    assert task.args == (123, "album-1", tmp_path)
    assert task.kwargs == {}


async def test_replace_preserves_media_name_and_creates_undo(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    uid = 1
    album = await insert_album(session, uid)
    album_dir = tmp_path
    original = create_test_jpeg(album_dir / VALID_NAME, 640, 480)
    media = await insert_album_media(
        session,
        uid,
        name=VALID_NAME,
        width=640,
        height=480,
    )
    media.byte_size = original.stat().st_size
    session.add(media)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    result = await replace_album_media_from_saved(
        session,
        album=album,
        album_dir=album_dir,
        media_name=VALID_NAME,
        saved=SavedInput(path=replacement, size=replacement.stat().st_size),
    )

    assert result.name == VALID_NAME
    row = await session.get_one(AlbumMedia, (uid, AID, VALID_NAME))
    assert row.width == 1600
    assert row.height == 1200
    assert row.upgrade_candidate is False
    snap = await session.get_one(AlbumMediaUndoSnapshot, (uid, AID, VALID_NAME))
    assert snap.expires_at > snap.created_at


async def test_replace_prunes_expired_undo_snapshots(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    uid = 1
    album = await insert_album(session, uid)
    album_dir = tmp_path
    original = create_test_jpeg(album_dir / VALID_NAME, 640, 480)
    await insert_album_media(session, uid, name=VALID_NAME, width=640, height=480)
    await insert_album_media(session, uid, name=OLD_NAME, width=640, height=480)
    undo_dir = album_dir / ".undo"
    undo_dir.mkdir()
    old_snapshot = undo_dir / OLD_NAME
    old_snapshot.write_bytes(b"expired snapshot")
    now = datetime.now(UTC)
    session.add(
        AlbumMediaUndoSnapshot(
            uid=uid,
            aid=AID,
            media_name=OLD_NAME,
            snapshot_path=str(Path(".undo") / OLD_NAME),
            upgrade_candidate=True,
            created_at=now - timedelta(minutes=10),
            expires_at=now - timedelta(minutes=5),
        )
    )
    media = await session.get_one(AlbumMedia, (uid, AID, VALID_NAME))
    media.byte_size = original.stat().st_size
    session.add(media)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    await replace_album_media_from_saved(
        session,
        album=album,
        album_dir=album_dir,
        media_name=VALID_NAME,
        saved=SavedInput(path=replacement, size=replacement.stat().st_size),
    )

    assert not old_snapshot.exists()
    assert await session.get(AlbumMediaUndoSnapshot, (uid, AID, OLD_NAME)) is None
    assert await session.get(AlbumMediaUndoSnapshot, (uid, AID, VALID_NAME)) is not None


async def test_replace_rejects_photo_video_mismatch(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    uid = 1
    album = await insert_album(session, uid)
    media = await insert_album_media(
        session,
        uid,
        name=VALID_NAME,
        width=640,
        height=480,
    )
    media.kind = "video"
    session.add(media)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    with pytest.raises(ValueError, match="Cannot replace video with photo"):
        await replace_album_media_from_saved(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
            saved=SavedInput(path=replacement, size=replacement.stat().st_size),
        )


async def test_video_replace_removes_generated_temp_poster(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    uid = 1
    album = await insert_album(session, uid)
    original = tmp_path / VALID_VIDEO_NAME
    original.write_bytes(b"old video")
    media = await insert_album_media(
        session,
        uid,
        name=VALID_VIDEO_NAME,
        width=640,
        height=480,
    )
    media.kind = "video"
    media.byte_size = original.stat().st_size
    session.add(media)
    replacement = tmp_path / "replacement.mp4"
    replacement.write_bytes(b"new video")
    replacement_poster = replacement.with_suffix(".jpg")
    replacement_poster.write_bytes(b"generated poster")
    await session.commit()

    with (
        patch(
            "app.logic.external_media.album_media.process_saved_media",
            AsyncMock(
                return_value=(
                    [Media(name=replacement.name, width=1280, height=720)],
                    [replacement],
                )
            ),
        ),
        patch(
            "app.logic.external_media.album_media.extract_frame",
            AsyncMock(),
        ),
    ):
        await replace_album_media_from_saved(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_VIDEO_NAME,
            saved=SavedInput(path=replacement, size=replacement.stat().st_size),
        )

    assert (tmp_path / VALID_VIDEO_NAME).read_bytes() == b"new video"
    assert not replacement_poster.exists()


async def test_video_undo_regenerates_restored_poster(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    uid = 1
    album = await insert_album(session, uid)
    target = tmp_path / VALID_VIDEO_NAME
    target.write_bytes(b"replacement video")
    target.with_suffix(".jpg").write_bytes(b"replacement poster")
    undo_dir = tmp_path / ".undo"
    undo_dir.mkdir()
    snapshot = undo_dir / VALID_VIDEO_NAME
    snapshot.write_bytes(b"original video")
    media = await insert_album_media(
        session,
        uid,
        name=VALID_VIDEO_NAME,
        width=1280,
        height=720,
    )
    media.kind = "video"
    media.byte_size = target.stat().st_size
    now = datetime.now(UTC)
    session.add(
        AlbumMediaUndoSnapshot(
            uid=uid,
            aid=AID,
            media_name=VALID_VIDEO_NAME,
            snapshot_path=str(Path(".undo") / VALID_VIDEO_NAME),
            upgrade_candidate=True,
            created_at=now,
            expires_at=now + timedelta(minutes=5),
        )
    )
    await session.commit()

    with (
        patch(
            "app.logic.external_media.undo.Media.probe",
            AsyncMock(return_value=Media(name=VALID_VIDEO_NAME, width=640, height=480)),
        ),
        patch(
            "app.logic.external_media.undo.extract_frame",
            AsyncMock(),
            create=True,
        ) as extract_frame,
    ):
        await restore_undo_snapshot(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_VIDEO_NAME,
        )

    extract_frame.assert_awaited_once_with(target)
