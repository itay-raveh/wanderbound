from __future__ import annotations

import shutil
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from app.logic.layout.media import is_video
from app.logic.panorama.storage import panorama_asset_paths

if TYPE_CHECKING:
    from app.models.album_media import PanoramaConfig

logger = structlog.get_logger(__name__)
type CleanupAction = tuple[str, Callable[[], Awaitable[object]]]
PENDING_CLEANUP_DIR = ".media-cleanup-pending"


def _pending_cleanup_root(album_dir: Path) -> Path:
    resolved_album = album_dir.resolve()
    pending_root = (resolved_album / PENDING_CLEANUP_DIR).resolve()
    try:
        pending_root.relative_to(resolved_album)
    except ValueError as error:
        raise ValueError(
            "Pending cleanup root must remain beneath the album"
        ) from error
    return pending_root


async def run_best_effort_cleanup(
    event: str,
    *actions: CleanupAction,
) -> None:
    for action_name, action in actions:
        try:
            await action()
        except BaseException:  # noqa: BLE001
            logger.warning(event, action=action_name, exc_info=True)


def register_workspace(album_dir: Path, workspace: Path) -> Path:
    if not workspace.exists():
        return workspace
    resolved_album = album_dir.resolve()
    resolved_workspace = workspace.resolve()
    try:
        resolved_workspace.relative_to(resolved_album)
    except ValueError as error:
        raise ValueError("Cleanup workspace must remain beneath the album") from error

    pending_root = _pending_cleanup_root(resolved_album)
    pending_root.mkdir(parents=True, exist_ok=True)
    return resolved_workspace.replace(pending_root / uuid.uuid4().hex)


def finalize_workspace(album_dir: Path, workspace: Path) -> None:
    if not workspace.exists():
        return
    pending_root = _pending_cleanup_root(album_dir)
    resolved_workspace = workspace.resolve()
    try:
        resolved_workspace.relative_to(pending_root)
    except ValueError as error:
        raise ValueError(
            "Cleanup workspace must be registered before removal"
        ) from error

    shutil.rmtree(resolved_workspace)
    with suppress(OSError):
        pending_root.rmdir()


def rebase_workspace_path(path: Path, source: Path, destination: Path) -> Path:
    try:
        relative = path.relative_to(source)
    except ValueError:
        return path
    return destination / relative


def sweep_pending_workspaces(album_dir: Path, cutoff: datetime) -> int:
    try:
        pending_root = _pending_cleanup_root(album_dir)
    except OSError, ValueError:
        logger.warning(
            "external_media.pending_cleanup_root_invalid",
            album_dir=str(album_dir),
            exc_info=True,
        )
        return 0
    if not pending_root.exists():
        return 0
    removed = 0
    for workspace in pending_root.iterdir():
        try:
            if workspace.is_symlink() or not workspace.is_dir():
                continue
            workspace.resolve().relative_to(pending_root)
            modified = datetime.fromtimestamp(workspace.stat().st_mtime, UTC)
            if modified > cutoff:
                continue
            shutil.rmtree(workspace)
            removed += 1
        except OSError, ValueError:
            logger.warning(
                "external_media.pending_cleanup_failed",
                workspace=str(workspace),
                exc_info=True,
            )
    with suppress(OSError):
        pending_root.rmdir()
    return removed


class MediaAssetTransition:
    def __init__(self, album_dir: Path, media_name: str) -> None:
        self.album_dir = album_dir
        self.media_name = media_name
        self.workspace = album_dir / ".media-transitions" / uuid.uuid4().hex
        self.staging_dir = self.workspace / "staged"
        self._previous: list[tuple[Path, Path]] = []
        self._activated: list[tuple[Path, Path]] = []

    def _current_assets(self, panorama: PanoramaConfig | None) -> list[Path]:
        target = self.album_dir / self.media_name
        assets = [target]
        if is_video(self.media_name) and target.with_suffix(".jpg").exists():
            assets.append(target.with_suffix(".jpg"))
        assets.extend(panorama_asset_paths(self.album_dir, self.media_name, panorama))
        return assets

    def _replacement_assets(
        self,
        replacement: Path,
        replacement_original: tuple[Path, Path] | None,
    ) -> list[tuple[Path, Path]]:
        target = self.album_dir / self.media_name
        assets = [(replacement, target)]
        replacement_poster = replacement.with_suffix(".jpg")
        if is_video(self.media_name) and replacement_poster.exists():
            assets.append((replacement_poster, target.with_suffix(".jpg")))
        if replacement_original is not None:
            assets.append(replacement_original)
        return assets

    def _backup(self, source: Path) -> None:
        backup = self.workspace / "previous" / source.relative_to(self.album_dir)
        backup.parent.mkdir(parents=True, exist_ok=True)
        source.replace(backup)
        self._previous.append((backup, source))

    def _install(self, staged: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(destination)
        self._activated.append((destination, staged))

    def activate(
        self,
        replacement: Path,
        panorama: PanoramaConfig | None,
        *,
        replacement_original: tuple[Path, Path] | None = None,
    ) -> None:
        try:
            for source in self._current_assets(panorama):
                if source.exists():
                    self._backup(source)
            for staged, destination in self._replacement_assets(
                replacement, replacement_original
            ):
                self._install(staged, destination)
        except BaseException:
            self.rollback()
            raise

    def rollback(self) -> None:
        for active, staged in reversed(self._activated):
            if active.exists():
                staged.parent.mkdir(parents=True, exist_ok=True)
                active.replace(staged)
        self._activated.clear()
        for backup, original in reversed(self._previous):
            if backup.exists():
                original.parent.mkdir(parents=True, exist_ok=True)
                backup.replace(original)
        self._previous.clear()
        self.discard()

    def register_cleanup(self) -> None:
        previous_workspace = self.workspace
        self.workspace = register_workspace(self.album_dir, self.workspace)
        self._previous = [
            (
                rebase_workspace_path(backup, previous_workspace, self.workspace),
                original,
            )
            for backup, original in self._previous
        ]
        self._activated = [
            (
                active,
                rebase_workspace_path(staged, previous_workspace, self.workspace),
            )
            for active, staged in self._activated
        ]

    def finish(self) -> None:
        finalize_workspace(self.album_dir, self.workspace)

    def discard(self) -> None:
        with suppress(FileNotFoundError):
            shutil.rmtree(self.workspace)
