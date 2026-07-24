"""Media upgrade orchestration: matching, download, replace, SSE events."""

from __future__ import annotations

import asyncio
import functools
import shutil
import subprocess
import threading
import time
from collections import Counter
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import anyio
import httpx
import structlog
from httpx_oauth.oauth2 import RefreshTokenError
from joblib import expires_after
from pydantic import BaseModel, Field, validate_call
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    import imagehash
    from joblib.memory import AsyncMemorizedFunc, MemorizedFunc

from app.core.db import get_engine
from app.core.http_clients import HttpClients
from app.core.observability import set_span_data, start_span
from app.core.resources import detect_cpu_count, detect_memory_mb
from app.core.worker_threads import run_sync
from app.logic.layout.media import Media, MediaName, is_video, media_limiter
from app.models.album_media import AlbumMedia
from app.models.google_photos import (
    GoogleMediaBaseUrl,
    GoogleMediaId,
    GoogleMediaType,
    PickedMediaItem,
    PickerSessionId,
)
from app.services.google_photos import (
    MAX_PHOTO_BYTES,
    AccessTokenGetter,
    delete_picker_session,
    download_media_bytes,
    download_media_to_file,
)

from .hash_cache import album_hash_memory, local_hash_cache
from .hashes import deserialize_media_hash, serialize_media_hash
from .phash_matching import (
    HashedMedia,
    MatchResult,
    MediaHash,
    compute_phash_from_bytes,
    deduplicate_items,
    match_media_globally,
)
from .processing import replace_photo, replace_video, tmp_file

logger = structlog.get_logger(__name__)

_UPGRADE_TMP_DIR = ".upgrade-tmp"
_UPGRADE_BASELINE_MB = 1024
_PER_UPGRADE_MB = 1024
_CANDIDATE_HASH_CACHE_TTL_HOURS = 24
_MAX_MATCH_PROGRESS_UPDATES = 100
_VIDEO_TRANSCODE_CONCURRENCY = 2


@functools.cache
def _hash_limiter() -> anyio.CapacityLimiter:
    return anyio.CapacityLimiter(min(8, detect_cpu_count()))


@functools.cache
def _upgrade_limiter() -> anyio.CapacityLimiter:
    memory_budget = detect_memory_mb() - _UPGRADE_BASELINE_MB
    return anyio.CapacityLimiter(max(1, memory_budget // _PER_UPGRADE_MB))


@functools.cache
def _video_upgrade_limiter() -> anyio.CapacityLimiter:
    return anyio.CapacityLimiter(_VIDEO_TRANSCODE_CONCURRENCY)


def _is_progress_checkpoint(done: int, total: int) -> bool:
    if total <= _MAX_MATCH_PROGRESS_UPDATES:
        return True
    previous = (done - 1) * _MAX_MATCH_PROGRESS_UPDATES // total
    current = done * _MAX_MATCH_PROGRESS_UPDATES // total
    return current != previous


@asynccontextmanager
async def _video_upgrade_slot(name: MediaName) -> AsyncIterator[None]:
    if not is_video(name):
        yield
        return
    async with _video_upgrade_limiter():
        yield


async def _cancel_tasks[T](tasks: list[asyncio.Task[T]]) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


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


async def _hash_local_one(
    album_dir: Path,
    name: str,
    cached_hash: MemorizedFunc,
) -> tuple[str, MediaHash | None]:
    """Hash one local file. Photos use one pHash; videos use sampled frames."""
    path = album_dir / name
    if not path.exists():
        return name, None
    try:
        stat = await run_sync(path.stat)
        return name, await run_sync(
            cached_hash,
            path,
            stat.st_size,
            stat.st_mtime_ns,
            limiter=_hash_limiter(),
        )
    # Pillow raises SyntaxError on corrupt/truncated image headers.
    except OSError, SyntaxError, subprocess.SubprocessError:
        logger.warning(
            "media_upgrade.local_hash_failed",
            exc_info=True,
        )
        return name, None


async def _compute_candidate_hash(
    _media_id: GoogleMediaId,
    media_type: GoogleMediaType,
    _create_time: str,
    _width: int | None,
    _height: int | None,
    _mime_type: str,
    *,
    base_url: GoogleMediaBaseUrl,
    download: httpx.AsyncClient,
    tokens: AccessTokenGetter,
) -> imagehash.ImageHash:
    thumb_param = "=w400-no" if media_type == "VIDEO" else "=w400"
    access_token = await tokens()
    thumb_bytes = await download_media_bytes(
        download, base_url, access_token, param=thumb_param
    )
    return await run_sync(
        compute_phash_from_bytes, thumb_bytes, limiter=_hash_limiter()
    )


def _candidate_hash_cache(
    album_dir: Path,
    cache_stats: Counter[str],
) -> AsyncMemorizedFunc:
    expiry = expires_after(hours=_CANDIDATE_HASH_CACHE_TTL_HOURS)
    cache_stats_lock = threading.Lock()

    def validate(metadata: dict[str, object]) -> bool:
        if not expiry(metadata):
            return False
        with cache_stats_lock:
            cache_stats["hits"] += 1
        return True

    return album_hash_memory(album_dir).cache(
        _compute_candidate_hash,
        ignore=["base_url", "download", "tokens"],
        cache_validation_callback=validate,
    )


async def _hash_candidate_one(
    download: httpx.AsyncClient,
    item: PickedMediaItem,
    tokens: AccessTokenGetter,
    cached_hash: AsyncMemorizedFunc,
) -> tuple[str, imagehash.ImageHash | None]:
    """Download one Google Photos thumbnail and compute its pHash."""
    try:
        return item.id, await cached_hash(
            item.id,
            item.type,
            item.create_time,
            item.media_file.width,
            item.media_file.height,
            item.media_file.mime_type,
            base_url=item.media_file.base_url,
            download=download,
            tokens=tokens,
        )
    except OSError, SyntaxError, httpx.HTTPError:
        logger.warning(
            "media_upgrade.candidate_hash_failed",
            exc_info=True,
        )
        return item.id, None


async def _hash_local_media(
    album_dir: Path,
    media_names: list[MediaName],
    cache_stats: Counter[str],
    persisted_local_hashes: Mapping[MediaName, list[str] | None],
) -> AsyncGenerator[tuple[int, MediaName, MediaHash | None, bool]]:
    cache_stats_lock = threading.Lock()

    def record_cache_hit(_metadata: dict[str, object]) -> bool:
        with cache_stats_lock:
            cache_stats["hits"] += 1
        return True

    completed = 0
    missing: list[MediaName] = []
    for name in media_names:
        serialized = persisted_local_hashes.get(name)
        if not serialized:
            missing.append(name)
            continue
        try:
            media_hash = deserialize_media_hash(serialized)
        except ValueError:
            missing.append(name)
            continue
        cache_stats["database_hits"] += 1
        yield completed, name, media_hash, True
        completed += 1

    if not missing:
        cache_stats["misses"] = 0
        return

    cached_hash = await run_sync(local_hash_cache, album_dir, record_cache_hit)

    async def _hash_one(name: MediaName) -> tuple[MediaName, MediaHash | None]:
        return await _hash_local_one(album_dir, name, cached_hash)

    tasks = [asyncio.create_task(_hash_one(name)) for name in missing]
    try:
        for coro in asyncio.as_completed(tasks):
            name, media_hash = await coro
            yield completed, name, media_hash, False
            completed += 1
    finally:
        await _cancel_tasks(tasks)

    cache_stats["misses"] = len(missing) - cache_stats["hits"]


async def _hash_candidate_media(
    album_dir: Path,
    download: httpx.AsyncClient,
    items: list[PickedMediaItem],
    tokens: AccessTokenGetter,
    cache_stats: Counter[str],
) -> AsyncGenerator[tuple[int, GoogleMediaId, imagehash.ImageHash | None]]:
    if not items:
        cache_stats["misses"] = 0
        return

    cached_hash = _candidate_hash_cache(album_dir, cache_stats)
    tasks = [
        asyncio.create_task(_hash_candidate_one(download, item, tokens, cached_hash))
        for item in items
    ]
    try:
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            item_id, media_hash = await coro
            yield i, item_id, media_hash
    finally:
        await _cancel_tasks(tasks)

    cache_stats["misses"] = len(items) - cache_stats["hits"]


async def _persist_local_hashes(
    uid: int,
    aid: str,
    hashes_by_name: Mapping[MediaName, list[str]],
) -> None:
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        rows = (
            await session.exec(
                select(AlbumMedia).where(
                    AlbumMedia.uid == uid,
                    AlbumMedia.aid == aid,
                    col(AlbumMedia.name).in_(tuple(hashes_by_name)),
                )
            )
        ).all()
        for row in rows:
            try:
                deserialize_media_hash(row.perceptual_hashes or [])
            except ValueError:
                pass
            else:
                continue
            row.perceptual_hashes = hashes_by_name[row.name]
            session.add(row)
        await session.commit()


async def _persist_local_hashes_best_effort(
    uid: int,
    aid: str,
    hashes_by_name: Mapping[MediaName, list[str]],
) -> None:
    try:
        await _persist_local_hashes(uid, aid, hashes_by_name)
    except SQLAlchemyError:
        logger.warning(
            "media_upgrade.local_hash_persist_failed",
            exc_info=True,
            user_id=uid,
            album_id=aid,
            count=len(hashes_by_name),
        )


async def run_matching(  # noqa: PLR0913, C901
    clients: HttpClients,
    album_dir: Path,
    media_by_step: dict[int, list[MediaName]],
    step_ids: list[int],
    google_items: list[PickedMediaItem],
    tokens: AccessTokenGetter,
    upgrade_candidates: set[MediaName] | None = None,
    persisted_local_hashes: Mapping[MediaName, list[str] | None] | None = None,
    uid: int | None = None,
    aid: str | None = None,
) -> AsyncGenerator[UpgradeEvent]:
    """Run the full matching pipeline, yielding SSE events for progress.

    Two-phase progress so the user sees counts matching their selection:
    "preparing" hashes local media, "matching" hashes picked Google items.
    Every unique local hash is loaded from the database or computed and backfilled.
    """
    matching_started = time.perf_counter()
    with start_span(
        "google_photos.matching",
        "Match Google Photos media",
        **{
            "app.workflow": "google_photos",
            "picked_media.count": len(google_items),
            "step.count": len(step_ids),
        },
    ) as span:
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
        media_names = list(
            dict.fromkeys(
                name for step_id in step_ids for name in media_by_step.get(step_id, [])
            )
        )
        set_span_data(
            span,
            **{
                "local_media.count": len(media_names),
                "unique_google_media.count": len(unique_items),
            },
        )

        local_hashes: dict[MediaName, MediaHash] = {}
        backfilled_hashes: dict[MediaName, list[str]] = {}
        local_cache_stats: Counter[str] = Counter()
        local_total = len(media_names)
        local_hash_started = time.perf_counter()
        with start_span(
            "google_photos.hash_local",
            "Hash local media",
            **{"app.workflow": "google_photos", "local_media.count": local_total},
        ):
            try:
                async for i, name, media_hash, from_database in _hash_local_media(
                    album_dir,
                    media_names,
                    local_cache_stats,
                    persisted_local_hashes or {},
                ):
                    if media_hash is not None:
                        local_hashes[name] = media_hash
                        if not from_database:
                            backfilled_hashes[name] = serialize_media_hash(media_hash)
                    done = i + 1
                    if _is_progress_checkpoint(done, local_total):
                        yield MatchInProgress(
                            phase="preparing", done=done, total=local_total
                        )
            finally:
                if backfilled_hashes and uid is not None and aid is not None:
                    await _persist_local_hashes_best_effort(uid, aid, backfilled_hashes)
            set_span_data(
                span,
                **{
                    "local_hash_database.hit_count": local_cache_stats["database_hits"],
                    "local_hash_cache.hit_count": local_cache_stats["hits"],
                    "local_hash_cache.miss_count": local_cache_stats["misses"],
                    "local_hash_backfill.count": len(backfilled_hashes),
                },
            )
        local_hash_ms = round((time.perf_counter() - local_hash_started) * 1000)

        candidate_hashes: dict[GoogleMediaId, imagehash.ImageHash] = {}
        candidate_cache_stats: Counter[str] = Counter()
        cand_total = len(unique_items)
        candidate_hash_started = time.perf_counter()
        with start_span(
            "google_photos.hash_candidates",
            "Hash Google Photos candidates",
            **{"app.workflow": "google_photos", "picked_media.count": cand_total},
        ):
            async for i, item_id, h in _hash_candidate_media(
                album_dir,
                clients.gphotos_download,
                unique_items,
                tokens,
                candidate_cache_stats,
            ):
                if h is not None:
                    candidate_hashes[item_id] = h
                done = i + 1
                if _is_progress_checkpoint(done, cand_total):
                    yield MatchInProgress(phase="matching", done=done, total=cand_total)
        candidate_hash_ms = round((time.perf_counter() - candidate_hash_started) * 1000)

        assignment_started = time.perf_counter()
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
        assignment_ms = round((time.perf_counter() - assignment_started) * 1000)

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
            "local_hash_database_hits": local_cache_stats["database_hits"],
            "local_hash_cache_hits": local_cache_stats["hits"],
            "local_hash_cache_misses": local_cache_stats["misses"],
            "local_hash_backfilled": len(backfilled_hashes),
            "candidate_hash_cache_hits": candidate_cache_stats["hits"],
            "candidate_hash_cache_misses": candidate_cache_stats["misses"],
            "local_hash_ms": local_hash_ms,
            "candidate_hash_ms": candidate_hash_ms,
            "assignment_ms": assignment_ms,
            "total_ms": round((time.perf_counter() - matching_started) * 1000),
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
                "local_hash_database.hit_count": diagnostics[
                    "local_hash_database_hits"
                ],
                "local_hash_backfill.count": diagnostics["local_hash_backfilled"],
                "candidate_hash_cache.hit_count": diagnostics[
                    "candidate_hash_cache_hits"
                ],
                "candidate_hash_cache.miss_count": diagnostics[
                    "candidate_hash_cache_misses"
                ],
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


async def run_upgrade(  # noqa: PLR0913, C901
    *,
    clients: HttpClients,
    uid: int,
    aid: str,
    album_dir: Path,
    matches: list[MatchResult],
    google_items_by_id: dict[GoogleMediaId, PickedMediaItem],
    upgrade_candidates: set[MediaName],
    local_dimensions: dict[MediaName, tuple[int, int]],
    tokens: AccessTokenGetter,
    session_ids: list[PickerSessionId],
) -> AsyncGenerator[UpgradeEvent]:
    """End-to-end upgrade: download + replace, persist results, release picker sessions.

    Owns the full post-validation lifecycle. Yields SSE events for streaming.
    Exceptions during streaming become ``UpgradeError`` events; persist and
    picker cleanup always run.
    """
    to_upgrade = [m for m in matches if _needs_upgrade(m, upgrade_candidates)]
    to_download: list[MatchResult] = []
    skipped_names: set[MediaName] = set()
    for match in to_upgrade:
        if _skip_from_picker_metadata(
            match,
            google_items_by_id,
            local_dimensions,
        ):
            skipped_names.add(match.local_name)
        else:
            to_download.append(match)
    total = len(to_download)
    succeeded: set[MediaName] = set()

    try:
        with start_span(
            "google_photos.upgrade",
            "Upgrade Google Photos media",
            **{
                "app.workflow": "google_photos",
                "user.id": uid,
                "album.id": aid,
                "match.count": len(matches),
                "upgrade.count": len(to_upgrade),
                "prefiltered.count": len(skipped_names),
                "download.count": total,
            },
        ) as span:
            if total == 0:
                set_span_data(span, result="empty" if not to_upgrade else "prefiltered")
                yield UpgradeCompleted(
                    replaced=0,
                    skipped=len(skipped_names),
                    failed=0,
                )
                return

            async with _upgrade_tmp(album_dir) as tmp_dir:

                async def _upgrade_one(match: MatchResult) -> MediaName | None:
                    item = google_items_by_id.get(match.google_id)
                    if not item:
                        return None
                    try:
                        async with (
                            _upgrade_limiter(),
                            _video_upgrade_slot(match.local_name),
                        ):
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
                    **{"app.workflow": "google_photos", "download.count": total},
                ):
                    tasks = [asyncio.create_task(_upgrade_one(m)) for m in to_download]
                    try:
                        for i, coro in enumerate(asyncio.as_completed(tasks)):
                            name = await coro
                            if name:
                                succeeded.add(name)
                            yield DownloadInProgress(done=i + 1, total=total)
                    finally:
                        await _cancel_tasks(tasks)

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
    _video_upgrade_limiter.cache_clear()
