"""Media upgrade orchestration and public event API."""

from __future__ import annotations

import asyncio
import functools
import shutil
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path

import anyio
import httpx
import structlog

from app.core.http_clients import HttpClients
from app.core.observability import set_span_data, start_span
from app.core.resources import detect_memory_mb
from app.core.worker_threads import run_sync
from app.logic.layout.media import MediaName
from app.models.google_photos import (
    GoogleMediaId,
    PickedMediaItem,
    PickerSessionId,
)
from app.services.google_photos import AccessTokenGetter

from .events import (
    DownloadInProgress,
    MatchCompleted,
    MatchInProgress,
    UpgradeCompleted,
    UpgradeEvent,
    UpgradeFailed,
)
from .matching import _clear_caches as _clear_matching_caches, run_matching
from .phash_matching import MatchResult
from .upgrade import (
    _cleanup_picker_sessions,
    _download_and_replace,
    _needs_upgrade,
    _persist_upgrade,
    _skip_from_picker_metadata,
    _upgrade_tmp,
)

__all__ = [
    "DownloadInProgress",
    "MatchCompleted",
    "MatchInProgress",
    "UpgradeCompleted",
    "UpgradeEvent",
    "UpgradeFailed",
    "cleanup_orphaned_tmp",
    "run_matching",
    "run_upgrade",
]

logger = structlog.get_logger(__name__)

_UPGRADE_TMP_DIR = ".upgrade-tmp"
_UPGRADE_BASELINE_MB = 1024
_PER_UPGRADE_MB = 1024


@functools.cache
def _upgrade_limiter() -> anyio.CapacityLimiter:
    memory_budget = detect_memory_mb() - _UPGRADE_BASELINE_MB
    return anyio.CapacityLimiter(max(1, memory_budget // _PER_UPGRADE_MB))


async def _cancel_tasks[T](tasks: list[asyncio.Task[T]]) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _upgrade_one(  # noqa: PLR0913
    clients: HttpClients,
    match: MatchResult,
    google_items_by_id: dict[GoogleMediaId, PickedMediaItem],
    album_dir: Path,
    tmp_dir: Path,
    tokens: AccessTokenGetter,
) -> tuple[MediaName | None, MediaName | None]:
    item = google_items_by_id.get(match.google_id)
    if not item:
        return None, None
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
        return None, None
    if replaced:
        return match.local_name, None
    return None, match.local_name


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
                with start_span(
                    "google_photos.download_replace",
                    "Download and replace media",
                    **{"app.workflow": "google_photos", "download.count": total},
                ):
                    tasks = [
                        asyncio.create_task(
                            _upgrade_one(
                                clients,
                                match,
                                google_items_by_id,
                                album_dir,
                                tmp_dir,
                                tokens,
                            )
                        )
                        for match in to_download
                    ]
                    try:
                        for i, coro in enumerate(asyncio.as_completed(tasks)):
                            succeeded_name, skipped_name = await coro
                            if succeeded_name:
                                succeeded.add(succeeded_name)
                            if skipped_name:
                                skipped_names.add(skipped_name)
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
    _clear_matching_caches()
    _upgrade_limiter.cache_clear()
