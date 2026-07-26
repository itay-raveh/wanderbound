from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.worker_threads import run_sync
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
from app.logic.panorama.storage import (
    preserve_panorama_original,
    remove_panorama_assets,
)
from app.models.album import Album
from app.models.album_media import AlbumMedia, PanoramaConfig

from .undo import create_undo_snapshot


class MediaNotFoundError(ValueError):
    pass


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
) -> PanoramaConfig | None:
    if (
        not isinstance(replacement, ImportedMedia)
        or replacement.panorama is None
        or replacement.source_path is None
    ):
        return None
    original = await run_sync(
        preserve_panorama_original,
        replacement.source_path,
        album_dir,
        media_name,
        limiter=media_limiter,
    )
    return replacement.panorama.model_copy(
        update={"original_path": str(original.relative_to(album_dir))}
    )


async def replace_album_media_from_saved(
    session: AsyncSession,
    *,
    album: Album,
    album_dir: Path,
    media_name: str,
    saved: SavedInput,
) -> AlbumMedia:
    row = await session.get(
        AlbumMedia,
        (album.uid, album.id, media_name),
        with_for_update=True,
    )
    if row is None:
        raise MediaNotFoundError("Media not found")
    written: list[Path] = []
    try:
        imported, written = await process_saved_media(
            album_dir=album_dir,
            saved=[saved],
        )
        replacement, replacement_path = _unpack_replacement(imported, written)
        _validate_replacement_kind(row, replacement.name)

        await create_undo_snapshot(
            session,
            uid=album.uid,
            aid=album.id,
            album_dir=album_dir,
            media_name=media_name,
        )
        target = album_dir / media_name
        await run_sync(shutil.move, replacement_path, target)
        if replacement_path.suffix == ".mp4":
            await run_sync(replacement_path.with_suffix(".jpg").unlink, missing_ok=True)
        written = []
        await run_sync(remove_panorama_assets, album_dir, media_name, row.panorama)
        row.panorama = await _replacement_panorama(replacement, album_dir, media_name)
        await run_sync(delete_thumbnails, target)
        if row.kind == "video":
            await extract_frame(target)

        row.width = replacement.width
        row.height = replacement.height
        row.byte_size = target.stat().st_size
        row.perceptual_hashes = await run_sync(
            try_compute_serialized_media_hash,
            target,
            limiter=media_limiter,
        )
        row.upgrade_candidate = False
        row.updated_at = datetime.now(UTC)
        session.add(row)
        await session.flush()
    except BaseException:
        await cleanup_imported_paths(written)
        raise
    else:
        return row
