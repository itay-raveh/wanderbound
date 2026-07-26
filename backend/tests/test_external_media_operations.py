from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks

from app.core.config import get_settings
from app.logic.external_media.album_media import replace_album_media_from_saved
from app.logic.external_media.files import (
    MediaAssetTransition,
    PendingMediaOperation,
    commit_media_operation,
)
from app.logic.external_media.undo import (
    UndoSnapshotUpdate,
    create_undo_snapshot,
    enqueue_undo_snapshot_prune,
    prune_all_expired_undo_snapshots,
    prune_expired_undo_snapshots,
    recover_pending_workspaces,
    restore_undo_snapshot,
    schedule_undo_snapshot_prune,
)
from app.logic.layout.media import Media
from app.logic.media_import import SavedInput
from app.logic.panorama.storage import remove_panorama_assets
from app.models.album import Album
from app.models.album_media import AlbumMedia, AlbumMediaUndoSnapshot, PanoramaConfig

from .factories import (
    AID,
    DEFAULT_MEDIA_NAME,
    MISSING_MEDIA_NAME,
    create_test_jpeg,
    insert_album,
    insert_album_media,
    make_user,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


VALID_NAME = DEFAULT_MEDIA_NAME
VALID_VIDEO_NAME = (
    "11111111-1111-4111-8111-111111111111_22222222-2222-4222-8222-222222222222.mp4"
)
VALID_VIDEO_POSTER_NAME = VALID_VIDEO_NAME.replace(".mp4", ".jpg")
OLD_NAME = MISSING_MEDIA_NAME


async def _commit_operation(
    session: AsyncSession,
    operation: PendingMediaOperation[AlbumMedia],
) -> AlbumMedia:
    await session.commit()
    await operation.finalize()
    return operation.result


async def test_commit_failure_attempts_every_compensation_and_preserves_error(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    _album, media = await _album_with_photo(session, tmp_path)
    first = AsyncMock(side_effect=OSError("first rollback failed"))
    second = AsyncMock()
    database_rollback = AsyncMock(side_effect=OSError("database rollback failed"))
    failed_session = MagicMock()
    failed_session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    failed_session.rollback = database_rollback
    operation = PendingMediaOperation(
        result=media,
        rollback_actions=(("first", first), ("second", second)),
        finalizers=(),
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        await commit_media_operation(failed_session, operation)

    first.assert_awaited_once_with()
    second.assert_awaited_once_with()
    database_rollback.assert_awaited_once_with()


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


def _active_panorama(original_path: str) -> PanoramaConfig:
    return PanoramaConfig(
        status="active",
        detection="gpano",
        source_width=4000,
        source_height=1000,
        cropped_area_width=4000,
        cropped_area_height=1000,
        full_pano_width=6000,
        captured_fov=240,
        perspective_fov=60,
        original_path=original_path,
        revision=3,
    )


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
    async def generate_poster(snapshot: Path) -> None:
        snapshot.with_suffix(".jpg").write_bytes(b"generated poster")

    with (
        patch(
            "app.logic.external_media.undo.Media.probe",
            AsyncMock(return_value=Media(name=VALID_VIDEO_NAME, width=640, height=480)),
        ),
        patch(
            "app.logic.external_media.undo.extract_frame",
            AsyncMock(side_effect=generate_poster),
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
    perceptual_hashes: list[str] | None = None,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    panorama: PanoramaConfig | None = None,
    original_snapshot_path: str | None = None,
) -> None:
    now = created_at or datetime.now(UTC)
    session.add(
        AlbumMediaUndoSnapshot(
            uid=uid,
            aid=AID,
            media_name=media_name,
            snapshot_path=str(Path(".undo") / media_name),
            perceptual_hashes=perceptual_hashes,
            panorama=panorama,
            original_snapshot_path=original_snapshot_path,
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
    album, media = await _album_with_photo(session, album_dir, uid=uid)
    media.perceptual_hashes = ["0000000000000000"]
    session.add(media)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    operation = await replace_album_media_from_saved(
        session,
        album=album,
        album_dir=album_dir,
        media_name=VALID_NAME,
        saved=_saved_input(replacement),
    )
    result = await _commit_operation(session, operation)

    assert result.name == VALID_NAME
    row = await session.get_one(AlbumMedia, (uid, AID, VALID_NAME))
    assert row.width == 1600
    assert row.height == 1200
    assert row.upgrade_candidate is False
    assert row.perceptual_hashes not in (None, ["0000000000000000"])
    snap = await session.get_one(AlbumMediaUndoSnapshot, (uid, AID, VALID_NAME))
    assert snap.expires_at > snap.created_at
    assert snap.perceptual_hashes == ["0000000000000000"]


async def test_replace_and_undo_restore_retained_panorama_original(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, media = await _album_with_photo(session, tmp_path)
    panorama_original = (
        tmp_path / ".panoramas" / "originals" / f"{Path(VALID_NAME).stem}.jpg"
    )
    panorama_original.parent.mkdir(parents=True)
    panorama_original.write_bytes(b"retained panorama original")
    preview = tmp_path / ".panoramas" / "preview" / f"{Path(VALID_NAME).stem}.jpg"
    preview.parent.mkdir(parents=True)
    preview.write_bytes(b"preview")
    rendered = (
        tmp_path
        / ".panoramas"
        / "rendered"
        / Path(VALID_NAME).stem
        / "3"
        / "800x400.jpg"
    )
    rendered.parent.mkdir(parents=True)
    rendered.write_bytes(b"rendered")
    panorama = _active_panorama(str(panorama_original.relative_to(tmp_path)))
    media.panorama = panorama
    session.add(media)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    operation = await replace_album_media_from_saved(
        session,
        album=album,
        album_dir=tmp_path,
        media_name=VALID_NAME,
        saved=_saved_input(replacement),
    )
    await _commit_operation(session, operation)

    snap = await session.get_one(AlbumMediaUndoSnapshot, (album.uid, AID, VALID_NAME))
    row = await session.get_one(AlbumMedia, (album.uid, AID, VALID_NAME))
    assert row.panorama is None
    assert snap.panorama == panorama
    assert snap.original_snapshot_path is not None
    assert (
        tmp_path / snap.original_snapshot_path
    ).read_bytes() == b"retained panorama original"
    assert not panorama_original.exists()
    assert not preview.exists()
    assert not rendered.exists()

    operation = await restore_undo_snapshot(
        session,
        album=album,
        album_dir=tmp_path,
        media_name=VALID_NAME,
    )
    restored = await _commit_operation(session, operation)

    assert restored.panorama == panorama
    assert panorama_original.read_bytes() == b"retained panorama original"
    assert (
        await session.get(AlbumMediaUndoSnapshot, (album.uid, AID, VALID_NAME)) is None
    )


async def test_replace_preserves_the_replacement_panorama_original(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, _media = await _album_with_photo(session, tmp_path)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 400)
    source_bytes = replacement.read_bytes()
    await session.commit()

    operation = await replace_album_media_from_saved(
        session,
        album=album,
        album_dir=tmp_path,
        media_name=VALID_NAME,
        saved=_saved_input(replacement),
    )
    replaced = await _commit_operation(session, operation)

    assert replaced.panorama is not None
    assert replaced.panorama.status == "suggested"
    assert replaced.panorama.original_path is not None
    assert (tmp_path / replaced.panorama.original_path).read_bytes() == source_bytes


async def test_replace_hash_failure_preserves_active_media_and_panorama_assets(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    primary_bytes = target.read_bytes()
    original = create_test_jpeg(
        tmp_path / ".panoramas" / "originals" / f"{target.stem}.jpg",
        2400,
        600,
    )
    preview = create_test_jpeg(
        tmp_path / ".panoramas" / "preview" / f"{target.stem}.jpg",
        800,
        200,
    )
    rendered = create_test_jpeg(
        tmp_path / ".panoramas" / "rendered" / target.stem / "3" / "800x400.jpg",
        800,
        400,
    )
    media.panorama = _active_panorama(str(original.relative_to(tmp_path)))
    session.add(media)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    with (
        patch(
            "app.logic.external_media.album_media.try_compute_serialized_media_hash",
            side_effect=OSError("hash failed"),
        ),
        pytest.raises(OSError, match="hash failed"),
    ):
        await replace_album_media_from_saved(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
            saved=_saved_input(replacement),
        )

    assert target.read_bytes() == primary_bytes
    assert original.exists()
    assert preview.exists()
    assert rendered.exists()


async def test_replace_flush_failure_restores_files_and_previous_snapshot_state(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    primary_bytes = target.read_bytes()
    original = create_test_jpeg(
        tmp_path / ".panoramas" / "originals" / f"{target.stem}.jpg",
        2400,
        600,
    )
    media.panorama = _active_panorama(str(original.relative_to(tmp_path)))
    session.add(media)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()
    real_flush = session.flush

    async def fail_after_activation(*args: object, **kwargs: object) -> None:
        if target.read_bytes() != primary_bytes:
            raise OSError("flush failed")
        await real_flush(*args, **kwargs)

    with (
        patch.object(session, "flush", side_effect=fail_after_activation),
        pytest.raises(OSError, match="flush failed"),
    ):
        await replace_album_media_from_saved(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
            saved=_saved_input(replacement),
        )

    assert target.read_bytes() == primary_bytes
    assert original.exists()
    assert not (tmp_path / ".undo" / VALID_NAME).exists()


async def test_replace_snapshot_finalizer_failure_keeps_successful_replacement(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, _media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    original_bytes = target.read_bytes()
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    with patch.object(
        UndoSnapshotUpdate,
        "finish",
        side_effect=OSError("snapshot cleanup failed"),
    ):
        operation = await replace_album_media_from_saved(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
            saved=_saved_input(replacement),
        )
        result = await _commit_operation(session, operation)

    assert result.width == 1600
    assert result.height == 1200
    assert target.read_bytes() != original_bytes
    assert (tmp_path / ".undo" / VALID_NAME).exists()


async def test_replace_pending_root_creation_failure_restores_previous_state(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    original_bytes = target.read_bytes()
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()
    real_mkdir = Path.mkdir

    def fail_pending_root(
        path: Path,
        *args: object,
        **kwargs: object,
    ) -> None:
        if path == tmp_path / ".media-cleanup-pending":
            raise OSError("pending root creation failed")
        real_mkdir(path, *args, **kwargs)

    with (
        patch.object(Path, "mkdir", autospec=True, side_effect=fail_pending_root),
        pytest.raises(OSError, match="pending root creation failed"),
    ):
        await replace_album_media_from_saved(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
            saved=_saved_input(replacement),
        )

    assert target.read_bytes() == original_bytes
    assert media.width == 640
    assert media.height == 480
    assert not (tmp_path / ".undo" / VALID_NAME).exists()


async def test_failed_finalizer_is_retried_by_album_prune(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, _media = await _album_with_photo(session, tmp_path)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()
    real_rmtree = shutil.rmtree

    def fail_transition_cleanup(path: Path) -> None:
        if ".media-transitions" in Path(path).parts or (
            ".media-cleanup-pending" in Path(path).parts
        ):
            raise OSError("cleanup failed")
        real_rmtree(path)

    with patch(
        "app.logic.external_media.files.shutil.rmtree",
        side_effect=fail_transition_cleanup,
    ):
        operation = await replace_album_media_from_saved(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
            saved=_saved_input(replacement),
        )
        await _commit_operation(session, operation)

    pending_root = tmp_path / ".media-cleanup-pending"
    pending = list(pending_root.iterdir())
    assert len(pending) == 2

    future = datetime.now(UTC) + timedelta(minutes=6)
    with patch(
        "app.logic.external_media.files.shutil.rmtree",
        side_effect=fail_transition_cleanup,
    ):
        await prune_expired_undo_snapshots(
            session,
            uid=album.uid,
            aid=album.id,
            album_dir=tmp_path,
            now=future,
        )
    assert all(path.exists() for path in pending)

    await recover_pending_workspaces(
        session,
        tmp_path,
        datetime.max.replace(tzinfo=UTC),
    )
    await prune_expired_undo_snapshots(
        session,
        uid=album.uid,
        aid=album.id,
        album_dir=tmp_path,
        now=future,
    )
    assert not pending_root.exists()


async def test_restart_before_replace_commit_restores_pending_operation(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, _media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    original_bytes = target.read_bytes()
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()
    transaction = await session.begin_nested()

    await replace_album_media_from_saved(
        session,
        album=album,
        album_dir=tmp_path,
        media_name=VALID_NAME,
        saved=_saved_input(replacement),
    )

    pending_root = tmp_path / ".media-cleanup-pending"
    assert len(list(pending_root.iterdir())) == 2
    await transaction.rollback()
    await recover_pending_workspaces(
        session,
        tmp_path,
        datetime.max.replace(tzinfo=UTC),
    )
    await prune_expired_undo_snapshots(
        session,
        uid=1,
        aid=AID,
        album_dir=tmp_path,
    )

    row = await session.get_one(AlbumMedia, (1, AID, VALID_NAME))
    assert row.width == 640
    assert row.height == 480
    assert target.read_bytes() == original_bytes
    assert not (tmp_path / ".undo" / VALID_NAME).exists()
    assert not pending_root.exists()


async def test_restart_after_replace_commit_finalizes_pending_operation(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, _media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    original_bytes = target.read_bytes()
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    await replace_album_media_from_saved(
        session,
        album=album,
        album_dir=tmp_path,
        media_name=VALID_NAME,
        saved=_saved_input(replacement),
    )
    await session.commit()

    pending_root = tmp_path / ".media-cleanup-pending"
    assert len(list(pending_root.iterdir())) == 2
    replacement_bytes = target.read_bytes()
    await recover_pending_workspaces(
        session,
        tmp_path,
        datetime.max.replace(tzinfo=UTC),
    )
    await prune_expired_undo_snapshots(
        session,
        uid=1,
        aid=AID,
        album_dir=tmp_path,
    )

    row = await session.get_one(AlbumMedia, (1, AID, VALID_NAME))
    assert row.width == 1600
    assert row.height == 1200
    assert replacement_bytes != original_bytes
    assert target.read_bytes() == replacement_bytes
    assert not pending_root.exists()


async def test_replace_rollback_failure_attempts_all_later_compensations(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    original_bytes = target.read_bytes()
    original_panorama = _active_panorama(
        str(Path(".panoramas") / "originals" / f"{target.stem}.jpg")
    )
    media.panorama = original_panorama
    session.add(media)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()
    real_flush = session.flush
    real_rollback = MediaAssetTransition.rollback

    async def fail_after_activation(*args: object, **kwargs: object) -> None:
        if target.read_bytes() != original_bytes:
            raise OSError("operation failed")
        await real_flush(*args, **kwargs)

    def rollback_then_fail(transition: MediaAssetTransition) -> None:
        real_rollback(transition)
        raise OSError("rollback failed")

    with (
        patch(
            "app.logic.external_media.album_media.process_saved_media",
            AsyncMock(
                return_value=(
                    [Media(name=replacement.name, width=1600, height=1200)],
                    [replacement],
                )
            ),
        ),
        patch.object(session, "flush", side_effect=fail_after_activation),
        patch.object(
            MediaAssetTransition,
            "rollback",
            autospec=True,
            side_effect=rollback_then_fail,
        ),
        pytest.raises(OSError, match="operation failed"),
    ):
        await replace_album_media_from_saved(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
            saved=_saved_input(replacement),
        )

    assert target.read_bytes() == original_bytes
    assert not (tmp_path / ".undo" / VALID_NAME).exists()
    assert media.width == 640
    assert media.height == 480
    assert media.panorama == original_panorama
    assert not replacement.exists()


async def test_repeated_snapshot_copy_failure_preserves_previous_snapshot(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, media = await _album_with_photo(session, tmp_path)
    undo_dir = tmp_path / ".undo"
    old_snapshot = create_test_jpeg(undo_dir / VALID_NAME, 320, 240)
    old_snapshot_bytes = old_snapshot.read_bytes()
    old_original_snapshot = create_test_jpeg(
        undo_dir / "panorama-originals" / f"{Path(VALID_NAME).stem}.jpg",
        1200,
        300,
    )
    old_original_bytes = old_original_snapshot.read_bytes()
    active_original = create_test_jpeg(
        tmp_path / ".panoramas" / "originals" / f"{Path(VALID_NAME).stem}.jpg",
        2400,
        600,
    )
    media.panorama = _active_panorama(str(active_original.relative_to(tmp_path)))
    session.add(media)
    _add_undo_snapshot(
        session,
        media_name=VALID_NAME,
        panorama=media.panorama,
        original_snapshot_path=str(old_original_snapshot.relative_to(tmp_path)),
    )
    await session.commit()
    real_copy2 = shutil.copy2

    def fail_retained_original(source: Path, target: Path) -> Path:
        if Path(source) == active_original:
            raise OSError("copy failed")
        return Path(real_copy2(source, target))

    with (
        patch(
            "app.logic.external_media.undo.shutil.copy2",
            side_effect=fail_retained_original,
        ),
        pytest.raises(OSError, match="copy failed"),
    ):
        await create_undo_snapshot(
            session,
            uid=album.uid,
            aid=album.id,
            album_dir=tmp_path,
            media_name=VALID_NAME,
        )

    assert old_snapshot.read_bytes() == old_snapshot_bytes
    assert old_original_snapshot.read_bytes() == old_original_bytes


async def test_snapshot_registration_failure_attempts_each_rollback_action(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, _media = await _album_with_photo(session, tmp_path)
    old_snapshot = create_test_jpeg(tmp_path / ".undo" / VALID_NAME, 320, 240)
    old_snapshot_bytes = old_snapshot.read_bytes()
    _add_undo_snapshot(session, media_name=VALID_NAME)
    await session.commit()
    snapshot_row = await session.get_one(
        AlbumMediaUndoSnapshot,
        (album.uid, album.id, VALID_NAME),
    )
    old_created_at = snapshot_row.created_at
    real_replace = Path.replace
    registration_failed = False

    def fail_registration_and_first_rollback(
        path: Path,
        target_path: Path,
    ) -> Path:
        nonlocal registration_failed
        target_path = Path(target_path)
        if ".staging" in path.parts and ".media-cleanup-pending" in target_path.parts:
            registration_failed = True
            raise OSError("registration failed")
        if (
            registration_failed
            and path == old_snapshot
            and ".staging" in target_path.parts
        ):
            raise OSError("rollback move failed")
        return real_replace(path, target_path)

    with (
        patch.object(
            Path,
            "replace",
            autospec=True,
            side_effect=fail_registration_and_first_rollback,
        ),
        pytest.raises(OSError, match="registration failed"),
    ):
        await create_undo_snapshot(
            session,
            uid=album.uid,
            aid=album.id,
            album_dir=tmp_path,
            media_name=VALID_NAME,
        )

    assert old_snapshot.read_bytes() == old_snapshot_bytes
    assert snapshot_row.created_at == old_created_at


async def test_undo_rejects_unreadable_original_snapshot_before_replacing_media(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    current_bytes = target.read_bytes()
    current_original = create_test_jpeg(
        tmp_path / ".panoramas" / "originals" / f"{target.stem}.jpg",
        2400,
        600,
    )
    media.panorama = _active_panorama(str(current_original.relative_to(tmp_path)))
    session.add(media)
    undo_dir = tmp_path / ".undo"
    create_test_jpeg(undo_dir / VALID_NAME, 1200, 900)
    unreadable_original = undo_dir / "panorama-originals" / f"{target.stem}.jpg"
    unreadable_original.mkdir(parents=True)
    _add_undo_snapshot(
        session,
        media_name=VALID_NAME,
        panorama=media.panorama,
        original_snapshot_path=str(unreadable_original.relative_to(tmp_path)),
    )
    await session.commit()

    with pytest.raises(ValueError, match="original snapshot"):
        await restore_undo_snapshot(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
        )

    assert target.read_bytes() == current_bytes
    assert current_original.exists()


async def test_undo_flush_failure_restores_current_and_snapshot_assets(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    current_bytes = target.read_bytes()
    current_original = create_test_jpeg(
        tmp_path / ".panoramas" / "originals" / f"{target.stem}.jpg",
        2400,
        600,
    )
    current_original_bytes = current_original.read_bytes()
    media.panorama = _active_panorama(str(current_original.relative_to(tmp_path)))
    session.add(media)
    snapshot = create_test_jpeg(tmp_path / ".undo" / VALID_NAME, 1200, 900)
    snapshot_bytes = snapshot.read_bytes()
    snapshot_original = create_test_jpeg(
        tmp_path / ".undo" / "panorama-originals" / f"{target.stem}.jpg",
        3600,
        900,
    )
    snapshot_original_bytes = snapshot_original.read_bytes()
    _add_undo_snapshot(
        session,
        media_name=VALID_NAME,
        panorama=media.panorama.model_copy(update={"source_width": 3600}),
        original_snapshot_path=str(snapshot_original.relative_to(tmp_path)),
    )
    await session.commit()

    with (
        patch.object(session, "flush", side_effect=OSError("flush failed")),
        pytest.raises(OSError, match="flush failed"),
    ):
        await restore_undo_snapshot(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
        )

    assert target.read_bytes() == current_bytes
    assert current_original.read_bytes() == current_original_bytes
    assert snapshot.read_bytes() == snapshot_bytes
    assert snapshot_original.read_bytes() == snapshot_original_bytes


async def test_undo_finalizer_failure_keeps_successful_restore(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, _media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    snapshot = create_test_jpeg(tmp_path / ".undo" / VALID_NAME, 1200, 900)
    snapshot_bytes = snapshot.read_bytes()
    _add_undo_snapshot(session, media_name=VALID_NAME)
    await session.commit()

    with patch.object(
        MediaAssetTransition,
        "finish",
        side_effect=OSError("transition cleanup failed"),
    ):
        operation = await restore_undo_snapshot(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
        )
        result = await _commit_operation(session, operation)

    assert result.width == 1200
    assert result.height == 900
    assert target.read_bytes() == snapshot_bytes
    assert not snapshot.exists()


async def test_restart_before_undo_commit_restores_pending_operation(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, _media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    current_bytes = target.read_bytes()
    snapshot = create_test_jpeg(tmp_path / ".undo" / VALID_NAME, 1200, 900)
    snapshot_bytes = snapshot.read_bytes()
    _add_undo_snapshot(session, media_name=VALID_NAME)
    await session.commit()
    transaction = await session.begin_nested()

    await restore_undo_snapshot(
        session,
        album=album,
        album_dir=tmp_path,
        media_name=VALID_NAME,
    )

    pending_root = tmp_path / ".media-cleanup-pending"
    assert len(list(pending_root.iterdir())) == 1
    await transaction.rollback()
    session.expire_all()
    assert await session.get(AlbumMediaUndoSnapshot, (1, AID, VALID_NAME)) is not None
    await recover_pending_workspaces(
        session,
        tmp_path,
        datetime.max.replace(tzinfo=UTC),
    )
    await prune_expired_undo_snapshots(
        session,
        uid=1,
        aid=AID,
        album_dir=tmp_path,
    )

    row = await session.get_one(AlbumMedia, (1, AID, VALID_NAME))
    assert row.width == 640
    assert row.height == 480
    assert target.read_bytes() == current_bytes
    assert snapshot.read_bytes() == snapshot_bytes
    assert not pending_root.exists()


async def test_restart_after_undo_commit_finalizes_pending_operation(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, _media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    current_bytes = target.read_bytes()
    snapshot = create_test_jpeg(tmp_path / ".undo" / VALID_NAME, 1200, 900)
    snapshot_bytes = snapshot.read_bytes()
    _add_undo_snapshot(session, media_name=VALID_NAME)
    await session.commit()

    await restore_undo_snapshot(
        session,
        album=album,
        album_dir=tmp_path,
        media_name=VALID_NAME,
    )
    await session.commit()

    pending_root = tmp_path / ".media-cleanup-pending"
    assert len(list(pending_root.iterdir())) == 1
    await recover_pending_workspaces(
        session,
        tmp_path,
        datetime.max.replace(tzinfo=UTC),
    )
    await prune_expired_undo_snapshots(
        session,
        uid=1,
        aid=AID,
        album_dir=tmp_path,
    )

    row = await session.get_one(AlbumMedia, (1, AID, VALID_NAME))
    assert row.width == 1200
    assert row.height == 900
    assert target.read_bytes() == snapshot_bytes
    assert target.read_bytes() != current_bytes
    assert await session.get(AlbumMediaUndoSnapshot, (1, AID, VALID_NAME)) is None
    assert not pending_root.exists()


async def test_undo_cleanup_registration_failure_restores_previous_state(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    current_bytes = target.read_bytes()
    snapshot = create_test_jpeg(tmp_path / ".undo" / VALID_NAME, 1200, 900)
    snapshot_bytes = snapshot.read_bytes()
    _add_undo_snapshot(session, media_name=VALID_NAME)
    await session.commit()
    real_replace = Path.replace

    def fail_registration(path: Path, target_path: Path) -> Path:
        target_path = Path(target_path)
        if (
            ".media-transitions" in path.parts
            and ".media-cleanup-pending" in target_path.parts
        ):
            raise OSError("cleanup registration failed")
        return real_replace(path, target_path)

    with (
        patch.object(Path, "replace", autospec=True, side_effect=fail_registration),
        pytest.raises(OSError, match="cleanup registration failed"),
    ):
        await restore_undo_snapshot(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
        )

    assert target.read_bytes() == current_bytes
    assert snapshot.read_bytes() == snapshot_bytes
    assert media.width == 640
    assert media.height == 480


async def test_undo_rollback_failure_still_restores_row_and_original_error(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    current_bytes = target.read_bytes()
    snapshot = create_test_jpeg(tmp_path / ".undo" / VALID_NAME, 1200, 900)
    snapshot_bytes = snapshot.read_bytes()
    _add_undo_snapshot(session, media_name=VALID_NAME)
    await session.commit()
    real_rollback = MediaAssetTransition.rollback

    def rollback_then_fail(transition: MediaAssetTransition) -> None:
        real_rollback(transition)
        raise OSError("rollback failed")

    with (
        patch.object(session, "flush", side_effect=OSError("operation failed")),
        patch.object(
            MediaAssetTransition,
            "rollback",
            autospec=True,
            side_effect=rollback_then_fail,
        ),
        pytest.raises(OSError, match="operation failed"),
    ):
        await restore_undo_snapshot(
            session,
            album=album,
            album_dir=tmp_path,
            media_name=VALID_NAME,
        )

    assert target.read_bytes() == current_bytes
    assert snapshot.read_bytes() == snapshot_bytes
    assert media.width == 640
    assert media.height == 480


async def test_expired_snapshot_rejects_original_path_outside_undo(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, _media = await _album_with_photo(session, tmp_path)
    target = tmp_path / VALID_NAME
    target_bytes = target.read_bytes()
    snapshot = create_test_jpeg(tmp_path / ".undo" / VALID_NAME, 320, 240)
    _add_undo_snapshot(
        session,
        media_name=VALID_NAME,
        original_snapshot_path=VALID_NAME,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    await session.commit()

    with pytest.raises(ValueError, match="Undo snapshot path"):
        await prune_expired_undo_snapshots(
            session,
            uid=album.uid,
            aid=album.id,
            album_dir=tmp_path,
        )

    assert target.read_bytes() == target_bytes
    assert snapshot.exists()


def test_panorama_directory_cleanup_propagates_io_failures(tmp_path: Path) -> None:
    rendered = tmp_path / ".panoramas" / "rendered" / Path(VALID_NAME).stem
    rendered.mkdir(parents=True)

    def fail_unless_ignored(path: Path, *, ignore_errors: bool = False) -> None:
        del path
        if not ignore_errors:
            raise PermissionError("cleanup failed")

    with (
        patch(
            "app.logic.panorama.storage.shutil.rmtree",
            side_effect=fail_unless_ignored,
        ),
        pytest.raises(PermissionError, match="cleanup failed"),
    ):
        remove_panorama_assets(tmp_path, VALID_NAME, None)


async def test_expired_panorama_undo_copy_does_not_delete_active_original(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album, media = await _album_with_photo(session, tmp_path)
    panorama_original = (
        tmp_path / ".panoramas" / "originals" / f"{Path(VALID_NAME).stem}.jpg"
    )
    panorama_original.parent.mkdir(parents=True)
    panorama_original.write_bytes(b"old retained original")
    media.panorama = _active_panorama(str(panorama_original.relative_to(tmp_path)))
    session.add(media)
    replacement = create_test_jpeg(tmp_path / "replacement.jpg", 1600, 1200)
    await session.commit()

    await replace_album_media_from_saved(
        session,
        album=album,
        album_dir=tmp_path,
        media_name=VALID_NAME,
        saved=_saved_input(replacement),
    )
    snapshot = await session.get_one(
        AlbumMediaUndoSnapshot, (album.uid, AID, VALID_NAME)
    )
    assert snapshot.original_snapshot_path is not None
    snapshot_original = tmp_path / snapshot.original_snapshot_path
    active_original = tmp_path / ".panoramas" / "originals" / "active.jpg"
    active_original.write_bytes(b"active original")
    snapshot.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.add(snapshot)
    await session.commit()

    removed = await prune_expired_undo_snapshots(
        session,
        uid=album.uid,
        aid=album.id,
        album_dir=tmp_path,
    )

    assert removed == 1
    assert not snapshot_original.exists()
    assert active_original.read_bytes() == b"active original"


async def test_prune_all_expired_undo_snapshots_uses_shared_user_folder(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    uid = 9091
    user = make_user(uid)
    session.add(user)
    await session.flush()
    await insert_album(session, uid)
    await insert_album_media(session, uid, name=VALID_NAME)
    album_dir = user.trips_folder / AID
    undo_dir = album_dir / ".undo"
    undo_dir.mkdir(parents=True)
    snapshot_path = undo_dir / VALID_NAME
    snapshot_path.write_bytes(b"snapshot")
    _add_undo_snapshot(
        session,
        uid=uid,
        media_name=VALID_NAME,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    await session.flush()

    removed = await prune_all_expired_undo_snapshots(session)

    assert removed == 1
    assert not snapshot_path.exists()
    assert await session.get(AlbumMediaUndoSnapshot, (uid, AID, VALID_NAME)) is None


async def test_global_prune_discovers_pending_cleanup_without_undo_snapshot(
    session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    uid = 9092
    user = make_user(uid)
    session.add(user)
    await insert_album(session, uid)
    album_dir = user.trips_folder / AID
    pending = album_dir / ".media-cleanup-pending" / "completed-workspace"
    pending.mkdir(parents=True)
    (pending / "prior-media.jpg").write_bytes(b"private media")
    await session.flush()

    removed = await prune_all_expired_undo_snapshots(
        session,
        now=datetime.now(UTC) + timedelta(minutes=6),
    )

    assert removed == 0
    assert not (album_dir / ".media-cleanup-pending").exists()


async def test_album_prune_removes_stale_marked_and_preserves_other_workspaces(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    active = tmp_path / ".media-transitions" / "active-workspace"
    unmarked = tmp_path / ".undo" / ".staging" / "unmarked-workspace"
    stale = tmp_path / ".media-cleanup-pending" / "stale-workspace"
    active.mkdir(parents=True)
    unmarked.mkdir(parents=True)
    stale.mkdir(parents=True)

    await prune_expired_undo_snapshots(
        session,
        uid=1,
        aid=AID,
        album_dir=tmp_path,
        now=datetime.now(UTC) + timedelta(minutes=6),
    )

    assert not stale.exists()
    assert active.exists()
    assert unmarked.exists()

    fresh = tmp_path / ".media-cleanup-pending" / "fresh-workspace"
    fresh.mkdir(parents=True)
    await prune_expired_undo_snapshots(
        session,
        uid=1,
        aid=AID,
        album_dir=tmp_path,
    )

    assert fresh.exists()


async def test_album_prune_does_not_follow_pending_root_outside_album(
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    album_dir = tmp_path / "album"
    album_dir.mkdir()
    outside = tmp_path / "outside" / "completed-workspace"
    outside.mkdir(parents=True)
    (outside / "private-media.jpg").write_bytes(b"private media")
    (album_dir / ".media-cleanup-pending").symlink_to(outside.parent)

    await prune_expired_undo_snapshots(
        session,
        uid=1,
        aid=AID,
        album_dir=album_dir,
        now=datetime.now(UTC) + timedelta(minutes=6),
    )

    assert outside.exists()


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
    _add_undo_snapshot(
        session,
        uid=uid,
        perceptual_hashes=["0123456789abcdef"],
    )
    await session.commit()

    extract_frame = await _restore_video_undo(session, album, tmp_path)

    assert poster.read_bytes() == b"custom poster"
    extract_frame.assert_not_awaited()
    row = await session.get_one(AlbumMedia, (uid, AID, VALID_VIDEO_NAME))
    assert row.perceptual_hashes == ["0123456789abcdef"]


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

    extract_frame.assert_awaited_once_with(tmp_path / ".undo" / VALID_VIDEO_NAME)
    assert target.with_suffix(".jpg").read_bytes() == b"generated poster"
