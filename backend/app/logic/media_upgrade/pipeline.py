"""Media upgrade orchestration: matching, download, replace, SSE events."""

from __future__ import annotations

import asyncio
import functools
import shutil
import subprocess
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import anyio
import httpx
import structlog
from httpx_oauth.oauth2 import RefreshTokenError
from pydantic import BaseModel, Field, validate_call
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    import imagehash

from app.core.db import get_engine
from app.core.http_clients import HttpClients
from app.core.observability import set_span_data, start_span
from app.core.resources import detect_cpu_count, detect_memory_mb
from app.core.worker_threads import run_sync
from app.logic.layout.media import Media, MediaName, is_video, media_limiter
from app.models.album_media import AlbumMedia
from app.models.google_photos import GoogleMediaId, PickedMediaItem, PickerSessionId
from app.services.google_photos import (
    MAX_PHOTO_BYTES,
    AccessTokenGetter,
    delete_picker_session,
    download_media_bytes,
    download_media_to_file,
)

from .phash_matching import (
    HashedMedia,
    MatchResult,
    MediaHash,
    bucket_by_window,
    build_step_windows,
    compute_phash_from_bytes,
    compute_phash_from_path,
    deduplicate_items,
    match_media_globally,
    relevant_media_names,
)
from .processing import (
    extract_video_frame_hashes,
    replace_photo,
    replace_video,
    tmp_file,
)

logger = structlog.get_logger(__name__)

_UPGRADE_TMP_DIR = ".upgrade-tmp"
_UPGRADE_BASELINE_MB = 1024
_PER_UPGRADE_MB = 1024


@functools.cache
def _hash_limiter() -> anyio.CapacityLimiter:
    return anyio.CapacityLimiter(min(8, detect_cpu_count()))


@functools.cache
def _upgrade_limiter() -> anyio.CapacityLimiter:
    memory_budget = detect_memory_mb() - _UPGRADE_BASELINE_MB
    return anyio.CapacityLimiter(max(1, memory_budget // _PER_UPGRADE_MB))


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


async def _hash_local_one(album_dir: Path, name: str) -> tuple[str, MediaHash | None]:
    """Hash one local file. Photos: single pHash. Videos: 4 sampled frames."""
    path = album_dir / name
    if not path.exists():
        return name, None
    try:
        if is_video(name):
            return name, await run_sync(
                extract_video_frame_hashes, path, limiter=_hash_limiter()
            )
        return name, await run_sync(
            compute_phash_from_path, path, limiter=_hash_limiter()
        )
    # Pillow raises SyntaxError on corrupt/truncated image headers.
    except OSError, SyntaxError, subprocess.SubprocessError:
        logger.warning(
            "media_upgrade.local_hash_failed",
            exc_info=True,
        )
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
        return item.id, await run_sync(
            compute_phash_from_bytes, thumb_bytes, limiter=_hash_limiter()
        )
    except OSError, SyntaxError, httpx.HTTPError:
        logger.warning(
            "media_upgrade.candidate_hash_failed",
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
    upgrade_candidates: set[MediaName] | None = None,
) -> AsyncGenerator[UpgradeEvent]:
    """Run the full matching pipeline, yielding SSE events for progress.

    Two-phase progress so the user sees counts matching their selection:
    "preparing" hashes local media, "matching" hashes picked Google items.
    Only media from steps that have picked Google items are hashed.
    """
    with start_span(
        "google_photos.matching",
        "Match Google Photos media",
        **{
            "app.workflow": "google_photos",
            "picked_media.count": len(google_items),
            "step.count": len(step_ids),
        },
    ) as span:
        windows = build_step_windows(step_timestamps, step_ids)
        google_by_window = bucket_by_window(google_items, windows)
        unique_items = deduplicate_items(
            [
                item
                for item in google_items
                if not (
                    item.type == "VIDEO"
                    and item.video_processing_status is not None
                    and item.video_processing_status != "READY"
                )
            ]
        )
        media_names = relevant_media_names(media_by_step, step_ids, google_by_window)
        set_span_data(
            span,
            **{
                "local_media.count": len(media_names),
                "unique_google_media.count": len(unique_items),
            },
        )

        local_hashes: dict[MediaName, MediaHash] = {}
        local_total = len(media_names)
        with start_span(
            "google_photos.hash_local",
            "Hash local media",
            **{"app.workflow": "google_photos", "local_media.count": local_total},
        ):
            local_tasks = [
                asyncio.create_task(_hash_local_one(album_dir, n)) for n in media_names
            ]
            for i, coro in enumerate(asyncio.as_completed(local_tasks)):
                name, h = await coro
                if h is not None:
                    local_hashes[name] = h
                yield MatchInProgress(phase="preparing", done=i + 1, total=local_total)

        candidate_hashes: dict[GoogleMediaId, imagehash.ImageHash] = {}
        cand_total = len(unique_items)
        with start_span(
            "google_photos.hash_candidates",
            "Hash Google Photos candidates",
            **{"app.workflow": "google_photos", "picked_media.count": cand_total},
        ):
            cand_tasks = [
                asyncio.create_task(
                    _hash_candidate_one(clients.gphotos_download, item, tokens)
                )
                for item in unique_items
            ]
            for i, coro in enumerate(asyncio.as_completed(cand_tasks)):
                item_id, h = await coro
                if h is not None:
                    candidate_hashes[item_id] = h
                yield MatchInProgress(phase="matching", done=i + 1, total=cand_total)

        with start_span(
            "google_photos.match_candidates",
            "Match media candidates",
            **{
                "app.workflow": "google_photos",
                "local_media.count": len(local_hashes),
                "candidate_hash.count": len(candidate_hashes),
            },
        ):
            hashed_locals = [
                HashedMedia(name, local_hashes[name], is_video(name))
                for name in media_names
                if name in local_hashes
            ]
            hashed_candidates = [
                HashedMedia(
                    item.id,
                    candidate_hashes[item.id],
                    item.type == "VIDEO",
                )
                for item in unique_items
                if item.id in candidate_hashes
            ]
            outcome = match_media_globally(hashed_locals, hashed_candidates)
            all_matches = outcome.matches
            if upgrade_candidates is not None:
                for match in all_matches:
                    match.upgraded = match.local_name not in upgrade_candidates

        diagnostics = {
            "picked": len(google_items),
            "matchable_picked": len(unique_items),
            "relevant_local": len(media_names),
            "local_hashed": len(local_hashes),
            "candidate_hashed": len(candidate_hashes),
            "valid_edges": outcome.diagnostics.valid_edges,
            "matched": len(all_matches),
            "unmatched_local": len(local_hashes) - len(all_matches),
            "nearest_13_to_15": outcome.diagnostics.nearest_13_to_15,
        }
        logger.info("google_photos.matching.completed", **diagnostics)
        set_span_data(
            span,
            **{
                "matched.count": len(all_matches),
                "unmatched.count": len(google_items) - len(all_matches),
                "matchable_picked.count": diagnostics["matchable_picked"],
                "relevant_local.count": diagnostics["relevant_local"],
                "local_hashed.count": diagnostics["local_hashed"],
                "candidate_hashed.count": diagnostics["candidate_hashed"],
                "valid_edges.count": diagnostics["valid_edges"],
                "unmatched_local.count": diagnostics["unmatched_local"],
                "nearest_13_to_15.count": diagnostics["nearest_13_to_15"],
            },
        )

        yield MatchCompleted(
            total_picked=len(google_items),
            matched=len(all_matches),
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
            updated = (
                await Media.probe(target)
                if is_video(match.local_name)
                else await run_sync(
                    Media.load,
                    target,
                    limiter=media_limiter,
                )
            )
        except OSError, SyntaxError, RuntimeError:
            logger.warning(
                "media_upgrade.reprobe_failed",
                exc_info=True,
            )
            continue
        row.width = updated.width
        row.height = updated.height
        row.byte_size = target.stat().st_size
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


async def run_upgrade(  # noqa: PLR0913, C901
    *,
    clients: HttpClients,
    uid: int,
    aid: str,
    album_dir: Path,
    matches: list[MatchResult],
    google_items_by_id: dict[GoogleMediaId, PickedMediaItem],
    upgrade_candidates: set[MediaName],
    tokens: AccessTokenGetter,
    session_ids: list[PickerSessionId],
) -> AsyncGenerator[UpgradeEvent]:
    """End-to-end upgrade: download + replace, persist results, release picker sessions.

    Owns the full post-validation lifecycle. Yields SSE events for streaming.
    Exceptions during streaming become ``UpgradeError`` events; persist and
    picker cleanup always run.
    """
    to_upgrade = [m for m in matches if _needs_upgrade(m, upgrade_candidates)]
    total = len(to_upgrade)
    succeeded: set[MediaName] = set()
    skipped_names: set[MediaName] = set()

    try:
        with start_span(
            "google_photos.upgrade",
            "Upgrade Google Photos media",
            **{
                "app.workflow": "google_photos",
                "user.id": uid,
                "album.id": aid,
                "match.count": len(matches),
                "upgrade.count": total,
            },
        ) as span:
            if total == 0:
                set_span_data(span, result="empty")
                yield UpgradeCompleted(replaced=0, skipped=0, failed=0)
                return

            async with _upgrade_tmp(album_dir) as tmp_dir:

                async def _upgrade_one(match: MatchResult) -> MediaName | None:
                    item = google_items_by_id.get(match.google_id)
                    if not item:
                        return None
                    try:
                        async with _upgrade_limiter():
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
                        logger.exception("media_upgrade.item_failed")
                        return None
                    if replaced:
                        return match.local_name
                    skipped_names.add(match.local_name)
                    return None

                with start_span(
                    "google_photos.download_replace",
                    "Download and replace media",
                    **{"app.workflow": "google_photos", "upgrade.count": total},
                ):
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
                    "media_upgrade.completed_with_failures",
                    failed=len(failed_names),
                )
            set_span_data(
                span,
                result="completed",
                **{
                    "replaced.count": len(succeeded),
                    "skipped.count": len(skipped_names),
                    "failed.count": len(failed_names),
                },
            )
            yield UpgradeCompleted(
                replaced=len(succeeded),
                skipped=len(skipped_names),
                failed=len(failed_names),
            )
    except Exception as exc:  # noqa: BLE001
        logger.error(  # noqa: TRY400
            "media_upgrade.failed",
            album_id=aid,
            error_type=type(exc).__name__,
        )
        yield UpgradeFailed(detail="Upgrade failed unexpectedly.")
    finally:
        await _persist_upgrade(
            uid,
            aid,
            album_dir,
            matches,
            succeeded,
        )
        await _cleanup_picker_sessions(clients.gphotos_picker, session_ids, tokens)


async def cleanup_orphaned_tmp(users_folder: Path) -> None:
    """Remove leftover .upgrade-tmp dirs from interrupted upgrades."""

    def _scan_and_remove() -> int:
        count = 0
        for tmp_dir in users_folder.glob(f"*/trip/*/{_UPGRADE_TMP_DIR}"):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            count += 1
        return count

    removed = await run_sync(_scan_and_remove)
    if removed:
        logger.info("media_upgrade.orphan_tmp_cleaned", removed=removed)


def _clear_caches() -> None:
    """Reset cached limiters (for test isolation across event loops)."""
    _hash_limiter.cache_clear()
    _upgrade_limiter.cache_clear()
