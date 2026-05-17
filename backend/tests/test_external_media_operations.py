from __future__ import annotations

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
from app.models.album import Album
from app.models.album_media import AlbumMedia, AlbumMediaUndoSnapshot

from .factories import (
    AID,
    DEFAULT_MEDIA_NAME,
    MISSING_MEDIA_NAME,
    create_test_jpeg,
    insert_album,
    insert_album_media,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


VALID_NAME = DEFAULT_MEDIA_NAME
VALID_VIDEO_NAME = (
    "11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.mp4"
)
VALID_VIDEO_POSTER_NAME = VALID_VIDEO_NAME.replace(".mp4", ".jpg")
OLD_NAME = MISSING_MEDIA_NAME


async def _album_with_photo(
    session: AsyncSession,
    tmp_path: Path,
    *,
    uid: int = 1,
    name: str = VALID_NAME,
    width: int = 640,
    height: int = 480,
) -> tuple[Album, AlbumMedia]:
    album = await insert_album(session, uid)
    original = create_test_jpeg(tmp_path / name, width, height)
    media = await insert_album_media(
        session,
        uid,
        name=name,
        width=width,
        height=height,
    )
    media.byte_size = original.stat().st_size
    session.add(media)
    return album, media


async def _album_with_video(
    session: AsyncSession,
    tmp_path: Path,
    *,
    uid: int = 1,
    content: bytes = b"old video",
    poster: bytes | None = None,
) -> tuple[Album, Path]:
    album = await insert_album(session, uid)
    target = tmp_path / VALID_VIDEO_NAME
    target.write_bytes(content)
    if poster is not None:
        target.with_suffix(".jpg").write_bytes(poster)
    media = await insert_album_media(
        session,
        uid,
        name=VALID_VIDEO_NAME,
        width=640,
        height=480,
    )
    media.kind = "video"
    media.byte_size = target.stat().st_size
    session.add(media)
    return album, target


def _replacement_video(tmp_path: Path, poster: bytes = b"generated poster") -> Path:
    replacement = tmp_path / "replacement.mp4"
    replacement.write_bytes(b"new video")
    replacement.with_suffix(".jpg").write_bytes(poster)
    return replacement


def _saved_input(path: Path) -> SavedInput:
    return SavedInput(path=path, size=path.stat().st_size)


async def _replace_video_with_mocked_processing(
    session: AsyncSession,
    album: Album,
    tmp_path: Path,
    replacement: Path,
) -> None:
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
        patch("app.logic.external_media.album_media.extract_frame", AsyncMock()),
    ):
        await replace_album_media_from_saved(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_VIDEO_NAME,
            saved=_saved_input(replacement),
        )


def _seed_video_undo_files(
    tmp_path: Path,
    target: Path,
    *,
    snapshot_poster: bytes | None = None,
) -> Path:
    target.with_suffix(".jpg").write_bytes(b"replacement poster")
    undo_dir = tmp_path / ".undo"
    undo_dir.mkdir()
    snapshot = undo_dir / VALID_VIDEO_NAME
    snapshot.write_bytes(b"original video")
    if snapshot_poster is not None:
        snapshot.with_suffix(".jpg").write_bytes(snapshot_poster)
    return target.with_suffix(".jpg")


async def _restore_video_undo(
    session: AsyncSession,
    album: Album,
    tmp_path: Path,
    *,
    create_frame_patch: bool = False,
) -> AsyncMock:
    with (
        patch(
            "app.logic.external_media.undo.Media.probe",
            AsyncMock(return_value=Media(name=VALID_VIDEO_NAME, width=640, height=480)),
        ),
        patch(
            "app.logic.external_media.undo.extract_frame",
            AsyncMock(),
            create=create_frame_patch,
        ) as extract_frame,
    ):
        await restore_undo_snapshot(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_VIDEO_NAME,
        )
    return extract_frame


def _add_undo_snapshot(
    session: AsyncSession,
    *,
    uid: int = 1,
    media_name: str = VALID_VIDEO_NAME,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> None:
    now = created_at or datetime.now(UTC)
    session.add(
        AlbumMediaUndoSnapshot(
            uid=uid,
            aid=AID,
            media_name=media_name,
            snapshot_path=str(Path(".undo") / media_name),
            upgrade_candidate=True,
            created_at=now,
            expires_at=expires_at or now + timedelta(minutes=5),
        )
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
    album_dir = tmp_path
    album, _media = await _album_with_photo(session, album_dir, uid=uid)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    result = await replace_album_media_from_saved(
        session,
        album=album,
        album_dir=album_dir,
        media_name=VALID_NAME,
        saved=_saved_input(replacement),
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
    album_dir = tmp_path
    album, _media = await _album_with_photo(session, album_dir, uid=uid)
    await insert_album_media(session, uid, name=OLD_NAME, width=640, height=480)
    undo_dir = album_dir / ".undo"
    undo_dir.mkdir()
    old_snapshot = undo_dir / OLD_NAME
    old_snapshot.write_bytes(b"expired snapshot")
    now = datetime.now(UTC)
    _add_undo_snapshot(
        session,
        uid=uid,
        media_name=OLD_NAME,
        created_at=now - timedelta(minutes=10),
        expires_at=now - timedelta(minutes=5),
    )
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    await replace_album_media_from_saved(
        session,
        album=album,
        album_dir=album_dir,
        media_name=VALID_NAME,
        saved=_saved_input(replacement),
    )

    assert not old_snapshot.exists()
    assert await session.get(AlbumMediaUndoSnapshot, (uid, AID, OLD_NAME)) is None
    assert await session.get(AlbumMediaUndoSnapshot, (uid, AID, VALID_NAME)) is not None


async def test_replace_rejects_photo_video_mismatch(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, media = await _album_with_photo(session, tmp_path)
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
            saved=_saved_input(replacement),
        )


async def test_video_replace_removes_generated_temp_poster(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, _target = await _album_with_video(session, tmp_path)
    replacement = _replacement_video(tmp_path)
    await session.commit()

    await _replace_video_with_mocked_processing(session, album, tmp_path, replacement)

    assert (tmp_path / VALID_VIDEO_NAME).read_bytes() == b"new video"
    assert not replacement.with_suffix(".jpg").exists()


async def test_video_replace_snapshots_custom_poster_for_undo(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, _target = await _album_with_video(session, tmp_path, poster=b"custom poster")
    replacement = _replacement_video(tmp_path)
    await session.commit()

    await _replace_video_with_mocked_processing(session, album, tmp_path, replacement)

    snapshot_poster = tmp_path / ".undo" / VALID_VIDEO_POSTER_NAME
    assert snapshot_poster.read_bytes() == b"custom poster"


async def test_video_undo_restores_snapshot_poster(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    uid = 1
    album, target = await _album_with_video(
        session, tmp_path, uid=uid, content=b"replacement video"
    )
    poster = _seed_video_undo_files(tmp_path, target, snapshot_poster=b"custom poster")
    _add_undo_snapshot(session, uid=uid)
    await session.commit()

    extract_frame = await _restore_video_undo(session, album, tmp_path)

    assert poster.read_bytes() == b"custom poster"
    extract_frame.assert_not_awaited()


async def test_video_undo_regenerates_restored_poster(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    uid = 1
    album, target = await _album_with_video(
        session, tmp_path, uid=uid, content=b"replacement video"
    )
    _seed_video_undo_files(tmp_path, target)
    _add_undo_snapshot(session, uid=uid)
    await session.commit()

    extract_frame = await _restore_video_undo(
        session, album, tmp_path, create_frame_patch=True
    )

    extract_frame.assert_awaited_once_with(target)
