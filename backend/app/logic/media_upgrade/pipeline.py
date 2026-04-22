"""Media upgrade orchestration: matching, download, replace, SSE events."""

from __future__ import annotations

import asyncio
import functools
import logging
import shutil
import subprocess
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import httpx
from httpx_oauth.oauth2 import RefreshTokenError
from pydantic import BaseModel, Field, validate_call
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    import imagehash

from app.core.db import get_engine
from app.core.http_clients import HttpClients
from app.core.resources import detect_cpu_count
from app.logic.layout.media import Media, MediaName, is_video
from app.models.album import Album
from app.models.google_photos import GoogleMediaId, PickedMediaItem, PickerSessionId
from app.services.google_photos import (
    MAX_PHOTO_BYTES,
    AccessTokenGetter,
    delete_picker_session,
    download_media_bytes,
    download_media_to_file,
)

from .phash_matching import (
    LocalHash,
    MatchResult,
    bucket_by_window,
    build_step_windows,
    compute_phash_from_bytes,
    compute_phash_from_path,
    cross_step_fallback,
    deduplicate_items,
    match_across_windows,
)
from .processing import (
    extract_video_frame_hashes,
    replace_photo,
    replace_video,
    tmp_file,
)

logger = logging.getLogger(__name__)

_UPGRADE_TMP_DIR = ".upgrade-tmp"


# @cache keeps the semaphore lazy so it binds to the running event loop, not
# import time. (Download concurrency is capped on the httpx client itself.)
@functools.cache
def _hash_sem() -> asyncio.Semaphore:
    return asyncio.Semaphore(min(8, detect_cpu_count()))


class MatchInProgress(BaseModel):
    type: Literal["match_in_progress"] = "match_in_progress"
    phase: str
    done: int
    total: int


class DownloadInProgress(BaseModel):
    type: Literal["download_in_progress"] = "download_in_progress"
    done: int
    total: int


class MatchCompleted(BaseModel):
    type: Literal["match_completed"] = "match_completed"
    total_picked: int
    matched: int
    already_upgraded: int
    unmatched: int
    matches: list[MatchResult]


class UpgradeCompleted(BaseModel):
    type: Literal["upgrade_completed"] = "upgrade_completed"
    replaced: int
    skipped: int
    failed: int


class UpgradeFailed(BaseModel):
    type: Literal["upgrade_failed"] = "upgrade_failed"
    detail: str


UpgradeEvent = Annotated[
    MatchInProgress
    | DownloadInProgress
    | MatchCompleted
    | UpgradeCompleted
    | UpgradeFailed,
    Field(discriminator="type"),
]


async def _hash_local_one(album_dir: Path, name: str) -> tuple[str, LocalHash | None]:
    """Hash one local file. Photos: single pHash. Videos: 4 sampled frames."""
    path = album_dir / name
    if not path.exists():
        return name, None
    try:
        async with _hash_sem():
            if is_video(name):
                return name, await asyncio.to_thread(extract_video_frame_hashes, path)
            return name, await asyncio.to_thread(compute_phash_from_path, path)
    # Pillow raises SyntaxError on corrupt/truncated image headers.
    except OSError, SyntaxError, subprocess.SubprocessError:
        logger.warning("Failed to hash %s", name, exc_info=True)
        return name, None


async def _hash_candidate_one(
    download: httpx.AsyncClient,
    item: PickedMediaItem,
    tokens: AccessTokenGetter,
) -> tuple[str, imagehash.ImageHash | None]:
    """Download one Google Photos thumbnail and compute its pHash."""
    try:
        thumb_param = "=w400-no" if item.type == "VIDEO" else "=w400"
        access_token = await tokens()
        thumb_bytes = await download_media_bytes(
            download, item.media_file.base_url, access_token, param=thumb_param
        )
        return item.id, await asyncio.to_thread(compute_phash_from_bytes, thumb_bytes)
    except OSError, SyntaxError, httpx.HTTPError:
        logger.warning(
            "Failed to download/hash thumbnail for %s",
            item.id,
            exc_info=True,
        )
        return item.id, None


async def run_matching(  # noqa: PLR0913
    clients: HttpClients,
    album_dir: Path,
    media_by_step: dict[int, list[MediaName]],
    step_timestamps: list[float],
    step_ids: list[int],
    google_items: list[PickedMediaItem],
    tokens: AccessTokenGetter,
    already_upgraded: dict[MediaName, GoogleMediaId] | None = None,
) -> AsyncGenerator[UpgradeEvent]:
    """Run the full matching pipeline, yielding SSE events for progress.

    Two-phase progress so the user sees counts matching their selection:
    "preparing" hashes local media, "matching" hashes picked Google items.
    Only media from steps that have picked Google items are hashed.
    """
    if already_upgraded is None:
        already_upgraded = {}

    # Bucket Google items by step windows (fast, no I/O)
    windows = build_step_windows(step_timestamps, step_ids)
    google_by_window = bucket_by_window(google_items, windows)
    all_window_items = [item for items in google_by_window.values() for item in items]
    unique_items = deduplicate_items(all_window_items)

    # Only hash local media from steps that have picked Google items.
    populated_steps = {sid for sid, items in google_by_window.items() if items}
    media_names = [
        name
        for sid in step_ids
        if sid in populated_steps
        for name in media_by_step.get(sid, [])
    ]

    # Phase 1: Hash local media (separate progress counter)
    local_hashes: dict[MediaName, LocalHash] = {}
    local_total = len(media_names)
    local_tasks = [
        asyncio.create_task(_hash_local_one(album_dir, n)) for n in media_names
    ]
    for i, coro in enumerate(asyncio.as_completed(local_tasks)):
        name, h = await coro
        if h is not None:
            local_hashes[name] = h
        yield MatchInProgress(phase="preparing", done=i + 1, total=local_total)

    # Phase 2: Download thumbnails and hash (progress scoped to picked items)
    candidate_hashes: dict[GoogleMediaId, imagehash.ImageHash] = {}
    cand_total = len(unique_items)
    cand_tasks = [
        asyncio.create_task(_hash_candidate_one(clients.gphotos_download, item, tokens))
        for item in unique_items
    ]
    for i, coro in enumerate(asyncio.as_completed(cand_tasks)):
        item_id, h = await coro
        if h is not None:
            candidate_hashes[item_id] = h
        yield MatchInProgress(phase="matching", done=i + 1, total=cand_total)

    # Phase 3: Hungarian match within windows + cross-step fallback (CPU only)
    all_matches, matched_locals, matched_candidates = match_across_windows(
        windows, google_by_window, media_names, local_hashes, candidate_hashes
    )
    cross_step_fallback(
        all_matches,
        matched_locals,
        matched_candidates,
        media_names,
        local_hashes,
        google_items,
        candidate_hashes,
    )

    already_upgraded_count = sum(
        1
        for m in all_matches
        if m.local_name in already_upgraded
        and already_upgraded[m.local_name] == m.google_id
    )

    yield MatchCompleted(
        total_picked=len(google_items),
        matched=len(all_matches),
        already_upgraded=already_upgraded_count,
        unmatched=len(google_items) - len(all_matches),
        matches=all_matches,
    )


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

    if is_video(local_name):
        param, replace, extra = "=dv", replace_video, {}
    else:
        param, replace, extra = "=d", replace_photo, {"max_bytes": MAX_PHOTO_BYTES}

    async with tmp_file(raw_path) as raw:
        access_token = await tokens()
        await download_media_to_file(
            download,
            item.media_file.base_url,
            access_token,
            raw,
            param=param,
            **extra,
        )
        return await replace(local_name, raw, tmp_path, target)


@asynccontextmanager
async def _upgrade_tmp(album_dir: Path) -> AsyncIterator[Path]:
    """Create and clean up the per-album tmp dir used during upgrade."""
    tmp_dir = album_dir / _UPGRADE_TMP_DIR
    await asyncio.to_thread(functools.partial(tmp_dir.mkdir, exist_ok=True))
    try:
        yield tmp_dir
    finally:
        await asyncio.to_thread(shutil.rmtree, tmp_dir, ignore_errors=True)


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
        async with AsyncSession(get_engine(), expire_on_commit=False) as session:
            album = await session.get_one(Album, (uid, aid))
            album.media, album.upgraded_media = await apply_upgrade_results(
                album_dir,
                matches,
                album.media,
                album.upgraded_media,
                succeeded,
            )
            session.add(album)
            await session.commit()
    except SQLAlchemyError:
        logger.warning(
            "Failed to persist upgrade results - filesystem ahead of DB, "
            "will self-heal on next upgrade attempt",
            exc_info=True,
            extra={"uid": uid, "aid": aid, "replaced": replaced},
        )
        return
    logger.info(
        "Persisted upgrade results",
        extra={"uid": uid, "aid": aid, "replaced": replaced},
    )


async def _cleanup_picker_sessions(
    picker: httpx.AsyncClient,
    session_ids: list[PickerSessionId],
    tokens: AccessTokenGetter,
) -> None:
    """Best-effort deletion of picker sessions after upgrade."""
    try:
        access_token = await tokens()
    except httpx.HTTPError, RefreshTokenError:
        logger.warning("Skipping picker session cleanup - token unavailable")
        return
    for sid in session_ids:
        try:
            await delete_picker_session(picker, sid, access_token)
        except httpx.HTTPError:
            logger.warning("Failed to delete picker session %s", sid)


async def run_upgrade(  # noqa: PLR0913, C901
    *,
    clients: HttpClients,
    uid: int,
    aid: str,
    album_dir: Path,
    matches: list[MatchResult],
    google_items_by_id: dict[GoogleMediaId, PickedMediaItem],
    already_upgraded: dict[MediaName, GoogleMediaId],
    tokens: AccessTokenGetter,
    session_ids: list[PickerSessionId],
) -> AsyncGenerator[UpgradeEvent]:
    """End-to-end upgrade: download + replace, persist results, release picker sessions.

    Owns the full post-validation lifecycle. Yields SSE events for streaming.
    Exceptions during streaming become ``UpgradeError`` events; persist and
    picker cleanup always run.
    """
    to_upgrade = [m for m in matches if m.local_name not in already_upgraded]
    total = len(to_upgrade)
    succeeded: set[MediaName] = set()
    skipped_names: set[MediaName] = set()

    try:
        if total == 0:
            yield UpgradeCompleted(replaced=0, skipped=0, failed=0)
            return

        async with _upgrade_tmp(album_dir) as tmp_dir:

            async def _upgrade_one(match: MatchResult) -> MediaName | None:
                item = google_items_by_id.get(match.google_id)
                if not item:
                    return None
                try:
                    replaced = await _download_and_replace(
                        clients.gphotos_download,
                        match.local_name,
                        item,
                        album_dir,
                        tmp_dir,
                        tokens,
                    )
                except (
                    OSError,
                    SyntaxError,
                    httpx.HTTPError,
                    RuntimeError,
                    subprocess.SubprocessError,
                ):
                    logger.exception("Failed to upgrade %s", match.local_name)
                    return None
                if replaced:
                    return match.local_name
                skipped_names.add(match.local_name)
                return None

            tasks = [asyncio.create_task(_upgrade_one(m)) for m in to_upgrade]
            try:
                for i, coro in enumerate(asyncio.as_completed(tasks)):
                    name = await coro
                    if name:
                        succeeded.add(name)
                    yield DownloadInProgress(done=i + 1, total=total)
            finally:
                for t in tasks:
                    t.cancel()
                # Wait for cancelled tasks before tmp cleanup runs.
                await asyncio.gather(*tasks, return_exceptions=True)

        failed_names = [
            m.local_name
            for m in to_upgrade
            if m.local_name not in succeeded and m.local_name not in skipped_names
        ]
        if failed_names:
            logger.warning(
                "Upgrade completed with %d failures: %s",
                len(failed_names),
                ", ".join(failed_names),
            )
        yield UpgradeCompleted(
            replaced=len(succeeded),
            skipped=len(skipped_names),
            failed=len(failed_names),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(  # noqa: TRY400
            "Upgrade failed for album %s: %s: %s", aid, type(exc).__name__, exc
        )
        yield UpgradeFailed(detail="Upgrade failed unexpectedly.")
    finally:
        await _persist_upgrade(uid, aid, album_dir, matches, succeeded)
        await _cleanup_picker_sessions(clients.gphotos_picker, session_ids, tokens)


async def apply_upgrade_results(
    album_dir: Path,
    matches: list[MatchResult],
    media: list[Media],
    upgraded_media: dict[MediaName, GoogleMediaId],
    succeeded: set[MediaName],
) -> tuple[list[Media], dict[MediaName, GoogleMediaId]]:
    """Re-probe replaced files and update media list + upgrade map.

    Only files in *succeeded* are marked as upgraded. Files that failed
    download or were skipped (e.g. not larger) are left untouched so
    the user can retry.
    """
    media_by_name = {m.name: m for m in media}
    new_upgraded = dict(upgraded_media)
    for match in matches:
        if match.local_name not in succeeded:
            continue
        target = album_dir / match.local_name
        if match.local_name not in media_by_name:
            continue
        try:
            if is_video(match.local_name):
                updated = await Media.probe(target)
            else:
                updated = await asyncio.to_thread(Media.load, target)
            media_by_name[match.local_name] = updated
        except OSError, SyntaxError, RuntimeError:
            logger.warning("Failed to re-probe %s", match.local_name, exc_info=True)
            continue
        new_upgraded[match.local_name] = match.google_id
    return list(media_by_name.values()), new_upgraded


async def cleanup_orphaned_tmp(users_folder: Path) -> None:
    """Remove leftover .upgrade-tmp dirs from interrupted upgrades."""

    def _scan_and_remove() -> int:
        count = 0
        for tmp_dir in users_folder.glob(f"*/trip/*/{_UPGRADE_TMP_DIR}"):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            count += 1
        return count

    removed = await asyncio.to_thread(_scan_and_remove)
    if removed:
        logger.info("Cleaned up %d orphaned upgrade-tmp dirs", removed)


def _clear_caches() -> None:
    """Reset cached semaphores (for test isolation across event loops)."""
    _hash_sem.cache_clear()
