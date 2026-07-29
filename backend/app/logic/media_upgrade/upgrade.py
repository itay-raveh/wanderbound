"""Download, replacement, persistence, and picker cleanup helpers."""

import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog
from httpx_oauth.oauth2 import RefreshTokenError
from pydantic import validate_call
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.core.observability import start_span
from app.core.worker_threads import run_sync
from app.logic.layout.media import Media, MediaName, media_limiter
from app.models.album_media import AlbumMedia, is_panorama_size
from app.models.google_photos import GoogleMediaId, PickedMediaItem, PickerSessionId
from app.services.google_photos import (
    MAX_PHOTO_BYTES,
    AccessTokenGetter,
    delete_picker_session,
    download_media_to_file,
)

from .phash_matching import MatchResult
from .processing import replace_photo, tmp_file

logger = structlog.get_logger(__name__)

_UPGRADE_TMP_DIR = ".upgrade-tmp"


@validate_call(config={"arbitrary_types_allowed": True})
async def _download_and_replace(  # noqa: PLR0913
    download: httpx.AsyncClient,
    local_name: MediaName,
    item: PickedMediaItem,
    album_dir: Path,
    tmp_dir: Path,
    tokens: AccessTokenGetter,
) -> bool:
    """Download one original, process, and replace the compressed file.

    ``local_name`` is validated against the strict ``MediaName`` pattern at
    the call boundary - this is the only place we build filesystem paths
    from a user-supplied filename, so traversal sequences are rejected here.

    Returns True if replaced, False if skipped (original not larger).
    """
    target = album_dir / local_name
    tmp_path = tmp_dir / local_name
    raw_path = tmp_dir / f"{local_name}.raw"

    async with tmp_file(raw_path) as raw:
        access_token = await tokens()
        await download_media_to_file(
            download,
            item.media_file.base_url,
            access_token,
            raw,
            param="=d",
            max_bytes=MAX_PHOTO_BYTES,
        )
        return await replace_photo(local_name, raw, tmp_path, target)


@asynccontextmanager
async def _upgrade_tmp(album_dir: Path) -> AsyncIterator[Path]:
    """Create and clean up the per-album tmp dir used during upgrade."""
    tmp_dir = album_dir / _UPGRADE_TMP_DIR
    await run_sync(tmp_dir.mkdir, exist_ok=True)
    try:
        yield tmp_dir
    finally:
        await run_sync(shutil.rmtree, tmp_dir, ignore_errors=True)


async def _persist_upgrade(
    uid: int,
    aid: str,
    album_dir: Path,
    matches: list[MatchResult],
    succeeded: set[MediaName],
) -> None:
    """Write upgrade results to DB after a successful disk replace.

    Called from the ``finally`` block of ``run_upgrade``, so it cannot
    yield events back to the client. If the commit fails the filesystem
    is ahead of the DB; drift self-heals on the user's next upgrade
    attempt (``_skip_smaller`` makes the re-replace a no-op, persist
    runs again). ``pool_pre_ping`` already handles idle-death at checkout.
    """
    if not succeeded:
        return
    replaced = len(succeeded)
    try:
        with start_span(
            "google_photos.persist_upgrade",
            "Persist Google Photos upgrade",
            **{
                "app.workflow": "google_photos",
                "user.id": uid,
                "album.id": aid,
                "replaced.count": replaced,
            },
        ):
            async with AsyncSession(get_engine(), expire_on_commit=False) as session:
                await _persist_upgrade_in_session(
                    session,
                    uid=uid,
                    aid=aid,
                    album_dir=album_dir,
                    matches=matches,
                    succeeded=succeeded,
                )
    except SQLAlchemyError:
        logger.warning(
            "media_upgrade.persist_failed",
            exc_info=True,
            user_id=uid,
            album_id=aid,
            replaced=replaced,
        )
        return
    logger.info(
        "google_photos.upgrade.completed",
        user_id=uid,
        album_id=aid,
        replaced=replaced,
    )


async def _persist_upgrade_in_session(  # noqa: PLR0913
    session: AsyncSession,
    *,
    uid: int,
    aid: str,
    album_dir: Path,
    matches: list[MatchResult],
    succeeded: set[MediaName],
) -> None:
    rows = {
        row.name: row
        for row in (
            await session.exec(
                select(AlbumMedia).where(
                    AlbumMedia.uid == uid,
                    AlbumMedia.aid == aid,
                    col(AlbumMedia.name).in_(tuple(succeeded)),
                )
            )
        ).all()
    }
    now = datetime.now(UTC)
    for match in matches:
        if match.local_name not in succeeded:
            continue
        row = rows.get(match.local_name)
        if row is None:
            continue
        target = album_dir / match.local_name
        try:
            updated = await run_sync(
                Media.load,
                target,
                limiter=media_limiter,
            )
        except OSError, SyntaxError, RuntimeError:
            logger.warning(
                "media_upgrade.reprobe_failed",
                exc_info=True,
            )
            continue
        row.width = updated.width
        row.height = updated.height
        if not is_panorama_size(updated.width, updated.height):
            row.panorama = None
        row.byte_size = target.stat().st_size
        row.perceptual_hashes = None
        row.upgrade_candidate = False
        row.updated_at = now
        session.add(row)
    await session.commit()


async def _cleanup_picker_sessions(
    picker: httpx.AsyncClient,
    session_ids: list[PickerSessionId],
    tokens: AccessTokenGetter,
) -> None:
    """Best-effort deletion of picker sessions after upgrade."""
    with start_span(
        "google_photos.cleanup_picker_sessions",
        "Clean up picker sessions",
        **{"app.workflow": "google_photos", "session.count": len(session_ids)},
    ):
        try:
            access_token = await tokens()
        except httpx.HTTPError, RefreshTokenError:
            logger.warning("google_photos.picker_cleanup_token_unavailable")
            return
        for sid in session_ids:
            try:
                await delete_picker_session(picker, sid, access_token)
            except httpx.HTTPError:
                logger.warning("google_photos.picker_session_delete_failed")


def _needs_upgrade(
    match: MatchResult,
    upgrade_candidates: set[MediaName],
) -> bool:
    return match.local_name in upgrade_candidates


def _skip_from_picker_metadata(
    match: MatchResult,
    google_items_by_id: dict[GoogleMediaId, PickedMediaItem],
    local_dimensions: dict[MediaName, tuple[int, int]],
) -> bool:
    item = google_items_by_id.get(match.google_id)
    local = local_dimensions.get(match.local_name)
    if item is None or local is None:
        return False

    google_width = item.media_file.width
    google_height = item.media_file.height
    local_width, local_height = local
    if (
        google_width is None
        or google_height is None
        or google_width <= 0
        or google_height <= 0
        or local_width <= 0
        or local_height <= 0
    ):
        return False
    if google_width * google_height > local_width * local_height:
        return False

    logger.info(
        "media_upgrade.skipped_by_metadata",
        media_name=match.local_name,
        google_width=google_width,
        google_height=google_height,
        local_width=local_width,
        local_height=local_height,
    )
    return True
