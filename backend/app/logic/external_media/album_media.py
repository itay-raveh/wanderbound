from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.worker_threads import run_sync
from app.logic.external_media.files import (
    CleanupAction,
    MediaAssetTransition,
    OperationWitness,
    PendingMediaOperation,
    run_best_effort_cleanup,
)
from app.logic.layout.media import (
    Media,
    delete_thumbnails,
    extract_frame,
    is_video,
    media_limiter,
)
from app.logic.media_import import (
    ImportedMedia,
    SavedInput,
    cleanup_imported_paths,
    process_saved_media,
)
from app.logic.media_upgrade.hashes import try_compute_serialized_media_hash
from app.logic.panorama.storage import preserve_panorama_original
from app.models.album import Album
from app.models.album_media import AlbumMedia, PanoramaConfig

from .undo import UndoSnapshotUpdate, create_undo_snapshot


class MediaNotFoundError(ValueError):
    pass


def _require_snapshot_update(
    update: UndoSnapshotUpdate | None,
) -> UndoSnapshotUpdate:
    if update is None:
        raise ValueError("Cannot replace a missing media asset")
    return update


async def _rollback_snapshot(update: UndoSnapshotUpdate | None) -> None:
    if update is not None:
        await update.rollback_best_effort()


def _finish_snapshot(update: UndoSnapshotUpdate | None) -> None:
    if update is not None:
        update.finish()


def _restore_row(row: AlbumMedia, values: dict[str, object]) -> None:
    for name, value in values.items():
        setattr(row, name, value)


def _unpack_replacement(
    imported: list[Media],
    written: list[Path],
) -> tuple[Media, Path]:
    if len(imported) != 1 or len(written) != 1:
        raise ValueError("Replacement must decode to exactly one media item")
    return imported[0], written[0]


def _validate_replacement_kind(row: AlbumMedia, replacement_name: str) -> None:
    if row.kind == "photo" and is_video(replacement_name):
        raise ValueError("Cannot replace photo with video")
    if row.kind == "video" and not is_video(replacement_name):
        raise ValueError("Cannot replace video with photo")


async def _replacement_panorama(
    replacement: Media,
    album_dir: Path,
    media_name: str,
    transition: MediaAssetTransition,
) -> tuple[PanoramaConfig | None, tuple[Path, Path] | None]:
    if (
        not isinstance(replacement, ImportedMedia)
        or replacement.panorama is None
        or replacement.source_path is None
    ):
        return None, None
    original = await run_sync(
        preserve_panorama_original,
        replacement.source_path,
        transition.staging_dir,
        media_name,
        limiter=media_limiter,
    )
    relative = original.relative_to(transition.staging_dir)
    destination = album_dir / relative
    return (
        replacement.panorama.model_copy(update={"original_path": str(relative)}),
        (original, destination),
    )


async def replace_album_media_from_saved(
    session: AsyncSession,
    *,
    album: Album,
    album_dir: Path,
    media_name: str,
    saved: SavedInput,
) -> PendingMediaOperation[AlbumMedia]:
    row = await session.get(
        AlbumMedia,
        (album.uid, album.id, media_name),
        with_for_update=True,
    )
    if row is None:
        raise MediaNotFoundError("Media not found")
    written: list[Path] = []
    transition = MediaAssetTransition(album_dir, media_name)
    snapshot_update: UndoSnapshotUpdate | None = None
    previous_values = {
        "width": row.width,
        "height": row.height,
        "byte_size": row.byte_size,
        "perceptual_hashes": row.perceptual_hashes,
        "panorama": row.panorama,
        "upgrade_candidate": row.upgrade_candidate,
        "updated_at": row.updated_at,
    }
    try:
        imported, written = await process_saved_media(
            album_dir=album_dir,
            saved=[saved],
        )
        replacement, replacement_path = _unpack_replacement(imported, written)
        _validate_replacement_kind(row, replacement.name)
        if is_video(media_name) and not replacement_path.with_suffix(".jpg").exists():
            await extract_frame(replacement_path)
        byte_size = replacement_path.stat().st_size
        perceptual_hashes = await run_sync(
            try_compute_serialized_media_hash,
            replacement_path,
            limiter=media_limiter,
        )
        replacement_panorama, replacement_original = await _replacement_panorama(
            replacement,
            album_dir,
            media_name,
            transition,
        )

        snapshot_update = await create_undo_snapshot(
            session,
            uid=album.uid,
            aid=album.id,
            album_dir=album_dir,
            media_name=media_name,
        )
        snapshot_update = _require_snapshot_update(snapshot_update)
        transition.set_recovery_witness(
            OperationWitness(
                album.uid,
                album.id,
                media_name,
                snapshot_update.snapshot.created_at,
            )
        )
        target = album_dir / media_name
        await run_sync(
            transition.activate,
            replacement_path,
            row.panorama,
            replacement_original=replacement_original,
        )
        await run_sync(delete_thumbnails, target)

        row.width = replacement.width
        row.height = replacement.height
        row.byte_size = byte_size
        row.perceptual_hashes = perceptual_hashes
        row.panorama = replacement_panorama
        row.upgrade_candidate = False
        row.updated_at = datetime.now(UTC)
        session.add(row)
        await run_sync(transition.register_cleanup)
        await session.flush()
    except BaseException:
        compensations: tuple[CleanupAction, ...] = (
            ("media_transition", partial(run_sync, transition.rollback)),
            ("undo_snapshot", partial(_rollback_snapshot, snapshot_update)),
            ("media_row", partial(run_sync, _restore_row, row, previous_values)),
            ("imported_files", partial(cleanup_imported_paths, written)),
        )
        await run_best_effort_cleanup(
            "external_media.replace_compensation_failed",
            *compensations,
        )
        raise
    else:
        return PendingMediaOperation(
            result=row,
            rollback_actions=(
                ("media_transition", partial(run_sync, transition.rollback)),
                ("undo_snapshot", snapshot_update.rollback_best_effort),
                ("media_row", partial(run_sync, _restore_row, row, previous_values)),
                ("imported_files", partial(cleanup_imported_paths, written)),
            ),
            finalizers=(
                ("media_transition", partial(run_sync, transition.finish)),
                ("undo_snapshot", partial(run_sync, _finish_snapshot, snapshot_update)),
            ),
        )
