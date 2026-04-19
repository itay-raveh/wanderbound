"""Media upgrade orchestration.

SSE event models, matching pipeline, and upgrade execution. Coordinates
the matching and processing modules, manages concurrency, and yields
SSE events for progress streaming.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import os
import shutil
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import httpx
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import imagehash

from app.logic.layout.media import Media, is_video
from app.models.google_photos import GoogleMediaId, MediaFilename
from app.services.google_photos import (
    PickedMediaItem,
    TokenProvider,
    download_media_bytes,
    download_media_to_file,
)

from .matching import (
    LocalHash,
    MatchResult,
    bucket_by_window,
    build_step_windows,
    compute_phash_from_bytes,
    compute_phash_from_path,
    cross_step_fallback,
    deduplicate_items,
    extract_video_frame_hashes,
    match_across_windows,
)
from .processing import replace_photo, replace_video

logger = logging.getLogger(__name__)

_UPGRADE_TMP_DIR = ".upgrade-tmp"


# ---------------------------------------------------------------------------
# Bounded concurrency
# ---------------------------------------------------------------------------

# Created lazily via @cache to avoid binding to the wrong event loop at import time.


@functools.cache
def _download_sem() -> asyncio.Semaphore:
    return asyncio.Semaphore(5)


@functools.cache
def _hash_sem() -> asyncio.Semaphore:
    return asyncio.Semaphore(min(8, (os.cpu_count() or 4)))


# ---------------------------------------------------------------------------
# SSE event models
# ---------------------------------------------------------------------------


class UpgradeMatching(BaseModel):
    type: Literal["matching"] = "matching"
    phase: str
    done: int
    total: int


class UpgradeDownloading(BaseModel):
    type: Literal["downloading"] = "downloading"
    done: int
    total: int


class UpgradeMatchSummary(BaseModel):
    type: Literal["match_summary"] = "match_summary"
    total_picked: int
    matched: int
    already_upgraded: int
    unmatched: int
    matches: list[MatchResult]


class UpgradeDone(BaseModel):
    type: Literal["done"] = "done"
    replaced: int
    skipped: int
    failed: int


class UpgradeError(BaseModel):
    type: Literal["error"] = "error"
    detail: str


UpgradeEvent = Annotated[
    UpgradeMatching
    | UpgradeDownloading
    | UpgradeMatchSummary
    | UpgradeDone
    | UpgradeError,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Hashing helpers (use semaphores + network)
# ---------------------------------------------------------------------------


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
    item: PickedMediaItem, tokens: TokenProvider
) -> tuple[str, imagehash.ImageHash | None]:
    """Download one Google Photos thumbnail and compute its pHash."""
    try:
        thumb_param = "=w400-no" if item.type == "VIDEO" else "=w400"
        async with _download_sem():
            access_token = await tokens.get()
            thumb_bytes = await download_media_bytes(
                item.media_file.base_url, access_token, param=thumb_param
            )
        return item.id, await asyncio.to_thread(compute_phash_from_bytes, thumb_bytes)
    except OSError, SyntaxError, httpx.HTTPError:
        logger.warning(
            "Failed to download/hash thumbnail for %s",
            item.id,
            exc_info=True,
        )
        return item.id, None


# ---------------------------------------------------------------------------
# Full matching pipeline
# ---------------------------------------------------------------------------


async def run_matching(  # noqa: PLR0913
    album_dir: Path,
    media_by_step: dict[int, list[MediaFilename]],
    step_timestamps: list[float],
    step_ids: list[int],
    google_items: list[PickedMediaItem],
    tokens: TokenProvider,
    already_upgraded: dict[MediaFilename, GoogleMediaId] | None = None,
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
    local_hashes: dict[MediaFilename, LocalHash] = {}
    local_total = len(media_names)
    local_tasks = [
        asyncio.create_task(_hash_local_one(album_dir, n)) for n in media_names
    ]
    for i, coro in enumerate(asyncio.as_completed(local_tasks)):
        name, h = await coro
        if h is not None:
            local_hashes[name] = h
        yield UpgradeMatching(phase="preparing", done=i + 1, total=local_total)

    # Phase 2: Download thumbnails and hash (progress scoped to picked items)
    candidate_hashes: dict[GoogleMediaId, imagehash.ImageHash] = {}
    cand_total = len(unique_items)
    cand_tasks = [
        asyncio.create_task(_hash_candidate_one(item, tokens)) for item in unique_items
    ]
    for i, coro in enumerate(asyncio.as_completed(cand_tasks)):
        item_id, h = await coro
        if h is not None:
            candidate_hashes[item_id] = h
        yield UpgradeMatching(phase="matching", done=i + 1, total=cand_total)

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

    yield UpgradeMatchSummary(
        total_picked=len(google_items),
        matched=len(all_matches),
        already_upgraded=already_upgraded_count,
        unmatched=len(google_items) - len(all_matches),
        matches=all_matches,
    )


# ---------------------------------------------------------------------------
# Upgrade execution (post-confirmation)
# ---------------------------------------------------------------------------


async def _download_and_replace(
    match: MatchResult,
    item: PickedMediaItem,
    album_dir: Path,
    tmp_dir: Path,
    tokens: TokenProvider,
) -> bool | None:
    """Download one original, process, and replace the compressed file.

    Returns True if replaced, False if skipped (original not larger),
    None if the download produced no data.
    """
    target = album_dir / match.local_name
    tmp_path = tmp_dir / match.local_name

    if is_video(match.local_name):
        raw_path = tmp_dir / f"{match.local_name}.raw"
        try:
            async with _download_sem():
                access_token = await tokens.get()
                await download_media_to_file(
                    item.media_file.base_url, access_token, raw_path, param="=dv"
                )
            return await replace_video(match.local_name, raw_path, tmp_path, target)
        except Exception:
            await asyncio.to_thread(lambda: raw_path.unlink(missing_ok=True))
            raise

    async with _download_sem():
        access_token = await tokens.get()
        data = await download_media_bytes(
            item.media_file.base_url, access_token, param="=d"
        )
    if not data:
        return None
    return await replace_photo(match.local_name, data, tmp_path, target)


async def execute_upgrade(  # noqa: PLR0913, C901
    album_dir: Path,
    matches: list[MatchResult],
    google_items_by_id: dict[GoogleMediaId, PickedMediaItem],
    tokens: TokenProvider,
    already_upgraded: dict[MediaFilename, GoogleMediaId],
    succeeded: set[MediaFilename] | None = None,
) -> AsyncGenerator[UpgradeEvent]:
    """Download originals and replace compressed files concurrently.

    Yields progress events for SSE streaming as each download completes.
    Successfully replaced filenames are added to *succeeded* (if provided)
    so the caller can persist only actual replacements.
    """
    if succeeded is None:
        succeeded = set()

    to_upgrade = [m for m in matches if m.local_name not in already_upgraded]
    total = len(to_upgrade)

    if total == 0:
        yield UpgradeDone(replaced=0, skipped=0, failed=0)
        return

    tmp_dir = album_dir / _UPGRADE_TMP_DIR
    tmp_dir.mkdir(exist_ok=True)

    async def _upgrade_one(match: MatchResult) -> MediaFilename | None:
        item = google_items_by_id.get(match.google_id)
        if not item:
            return None
        try:
            result = await _download_and_replace(
                match, item, album_dir, tmp_dir, tokens
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
        if result is True:
            return match.local_name
        if result is False:
            skipped_names.add(match.local_name)
        return None

    skipped_names: set[str] = set()
    upgrade_tasks = [asyncio.create_task(_upgrade_one(m)) for m in to_upgrade]
    replaced = 0
    completed = False

    try:
        for i, coro in enumerate(asyncio.as_completed(upgrade_tasks)):
            name = await coro
            if name:
                replaced += 1
                succeeded.add(name)
            yield UpgradeDownloading(done=i + 1, total=total)
        completed = True
    finally:
        for t in upgrade_tasks:
            t.cancel()
        # Wait for cancelled tasks to finish before cleaning up tmp files
        # they may still be writing to.
        await asyncio.gather(*upgrade_tasks, return_exceptions=True)
        with contextlib.suppress(OSError):
            for leftover in tmp_dir.iterdir():
                leftover.unlink(missing_ok=True)
            tmp_dir.rmdir()

    if completed:
        skipped = len(skipped_names)
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
        yield UpgradeDone(
            replaced=replaced,
            skipped=skipped,
            failed=len(failed_names),
        )


# ---------------------------------------------------------------------------
# Post-upgrade DB helpers
# ---------------------------------------------------------------------------


async def apply_upgrade_results(
    album_dir: Path,
    matches: list[MatchResult],
    media: list[Media],
    upgraded_media: dict[MediaFilename, GoogleMediaId],
    succeeded: set[MediaFilename],
) -> tuple[list[Media], dict[MediaFilename, GoogleMediaId]]:
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
    _download_sem.cache_clear()
    _hash_sem.cache_clear()
