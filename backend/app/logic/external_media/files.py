from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

import structlog

from app.logic.layout.media import is_video
from app.logic.panorama.storage import panorama_asset_paths

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.album_media import PanoramaConfig

logger = structlog.get_logger(__name__)
type CleanupAction = tuple[str, Callable[[], Awaitable[object]]]
PENDING_CLEANUP_DIR = ".media-cleanup-pending"
RECOVERY_MANIFEST = ".recovery.json"
RECOVERY_READY = ".recovery-ready"
COMMITTED_MARKER = ".committed"


@dataclass(frozen=True)
class OperationWitness:
    uid: int
    aid: str
    media_name: str
    snapshot_created_at: datetime | None


@dataclass(frozen=True)
class PendingMediaOperation[T]:
    result: T
    rollback_actions: tuple[CleanupAction, ...]
    finalizers: tuple[CleanupAction, ...]

    async def rollback(self) -> None:
        await run_best_effort_cleanup(
            "external_media.commit_compensation_failed",
            *self.rollback_actions,
        )

    async def finalize(self) -> None:
        await run_best_effort_cleanup(
            "external_media.commit_finalization_failed",
            *self.finalizers,
        )


async def commit_media_operation[T](
    session: AsyncSession,
    operation: PendingMediaOperation[T],
) -> T:
    try:
        await session.commit()
    except BaseException:
        await run_best_effort_cleanup(
            "external_media.commit_compensation_failed",
            ("filesystem", operation.rollback),
            ("database", session.rollback),
        )
        raise
    await operation.finalize()
    return operation.result


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


def _relative_path(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError("Recovery path must remain beneath its root") from error
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Recovery path must remain beneath its root")
    return str(relative)


def write_recovery_manifest(
    album_dir: Path,
    workspace: Path,
    witness: OperationWitness,
    previous: list[tuple[Path, Path]],
    activated: list[tuple[Path, Path]],
) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    previous_by_original = {original: backup for backup, original in previous}
    payload = {
        "version": 1,
        "witness": {
            "uid": witness.uid,
            "aid": witness.aid,
            "media_name": witness.media_name,
            "snapshot_created_at": (
                witness.snapshot_created_at.isoformat()
                if witness.snapshot_created_at is not None
                else None
            ),
        },
        "previous": [
            {
                "backup": _relative_path(backup, workspace),
                "original": _relative_path(original, album_dir),
            }
            for backup, original in previous
        ],
        "activated": [
            {
                "destination": _relative_path(destination, album_dir),
                "staged": (
                    None
                    if witness.snapshot_created_at is not None
                    or staged.is_relative_to(workspace)
                    else _relative_path(staged, album_dir)
                ),
                "backup": (
                    _relative_path(previous_by_original[destination], workspace)
                    if destination in previous_by_original
                    else None
                ),
            }
            for destination, staged in activated
        ],
    }
    temporary = workspace / f"{RECOVERY_MANIFEST}.{uuid.uuid4().hex}.tmp"
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(workspace / RECOVERY_MANIFEST)


def mark_recovery_ready(workspace: Path) -> None:
    (workspace / RECOVERY_READY).touch(exist_ok=True)


def mark_workspace_committed(workspace: Path) -> None:
    (workspace / COMMITTED_MARKER).touch(exist_ok=True)


def _remove_recovery_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"Invalid media recovery {label}")
    return cast("dict[str, object]", value)


def _load_recovery_manifest(workspace: Path) -> dict[str, object] | None:
    manifest = workspace / RECOVERY_MANIFEST
    if not manifest.is_file() or manifest.is_symlink():
        return None
    payload: object = json.loads(manifest.read_text(encoding="utf-8"))
    parsed = _mapping(payload, "manifest")
    if parsed.get("version") != 1:
        raise ValueError("Unsupported media recovery manifest")
    return parsed


def recovery_witness(workspace: Path) -> OperationWitness | None:
    payload = _load_recovery_manifest(workspace)
    if payload is None:
        return None
    raw = _mapping(payload.get("witness"), "witness")
    uid = raw.get("uid")
    aid = raw.get("aid")
    media_name = raw.get("media_name")
    created_at = raw.get("snapshot_created_at")
    if (
        not isinstance(uid, int)
        or not isinstance(aid, str)
        or not isinstance(media_name, str)
        or (created_at is not None and not isinstance(created_at, str))
    ):
        raise ValueError("Invalid media recovery witness")
    return OperationWitness(
        uid=uid,
        aid=aid,
        media_name=media_name,
        snapshot_created_at=(
            datetime.fromisoformat(created_at) if created_at is not None else None
        ),
    )


def _manifest_path(root: Path, value: object) -> Path:
    if not isinstance(value, str):
        raise TypeError("Invalid media recovery path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Invalid media recovery path")
    path = root / relative
    path.resolve().relative_to(root.resolve())
    return path


def _recover_activated(
    album_dir: Path,
    workspace: Path,
    activated: Sequence[object],
) -> None:
    for raw in reversed(activated):
        move = _mapping(raw, "move")
        destination = _manifest_path(album_dir, move.get("destination"))
        backup = move.get("backup")
        if backup is not None and not _manifest_path(workspace, backup).exists():
            continue
        if not destination.exists():
            continue
        staged = move.get("staged")
        if staged is None:
            _remove_recovery_path(destination)
        else:
            staged_path = _manifest_path(album_dir, staged)
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            destination.replace(staged_path)


def _recover_previous(
    album_dir: Path,
    workspace: Path,
    previous: Sequence[object],
) -> None:
    for raw in reversed(previous):
        move = _mapping(raw, "move")
        backup = _manifest_path(workspace, move.get("backup"))
        if backup.exists():
            original = _manifest_path(album_dir, move.get("original"))
            original.parent.mkdir(parents=True, exist_ok=True)
            backup.replace(original)


def recover_workspace(album_dir: Path, workspace: Path, *, committed: bool) -> None:
    payload = _load_recovery_manifest(workspace)
    if payload is None:
        if committed:
            _remove_recovery_path(workspace)
        return
    if committed or (workspace / COMMITTED_MARKER).is_file():
        _remove_recovery_path(workspace)
        return
    previous = payload.get("previous")
    activated = payload.get("activated")
    if not isinstance(previous, list) or not isinstance(activated, list):
        raise TypeError("Invalid media recovery manifest")
    if (workspace / RECOVERY_READY).is_file():
        _recover_activated(album_dir, workspace, activated)
    _recover_previous(album_dir, workspace, previous)
    _remove_recovery_path(workspace)


def recovery_workspaces(
    album_dir: Path,
    cutoff: datetime,
) -> list[Path]:
    try:
        pending_root = _pending_cleanup_root(album_dir)
    except OSError, ValueError:
        logger.warning(
            "external_media.pending_cleanup_root_invalid",
            album_dir=str(album_dir),
            exc_info=True,
        )
        return []
    roots = (
        pending_root,
        album_dir / ".media-transitions",
        album_dir / ".undo" / ".staging",
    )
    workspaces: list[Path] = []
    for root in roots:
        if not root.exists() or root.is_symlink():
            continue
        for workspace in root.iterdir():
            try:
                if workspace.is_symlink() or not workspace.is_dir():
                    continue
                modified = datetime.fromtimestamp(workspace.stat().st_mtime, UTC)
                if (
                    modified <= cutoff
                    and _load_recovery_manifest(workspace) is not None
                ):
                    workspaces.append(workspace)
            except OSError, TypeError, ValueError, json.JSONDecodeError:
                logger.warning(
                    "external_media.recovery_manifest_invalid",
                    workspace=str(workspace),
                    exc_info=True,
                )
    return workspaces


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
            if (workspace / RECOVERY_MANIFEST).exists():
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
        self._witness: OperationWitness | None = None

    def set_recovery_witness(self, witness: OperationWitness) -> None:
        self._witness = witness

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
            current_assets = [
                source for source in self._current_assets(panorama) if source.exists()
            ]
            replacement_assets = self._replacement_assets(
                replacement, replacement_original
            )
            if self._witness is not None:
                planned_previous = [
                    (
                        self.workspace
                        / "previous"
                        / source.relative_to(self.album_dir),
                        source,
                    )
                    for source in current_assets
                ]
                write_recovery_manifest(
                    self.album_dir,
                    self.workspace,
                    self._witness,
                    planned_previous,
                    [
                        (destination, staged)
                        for staged, destination in replacement_assets
                    ],
                )
            for source in current_assets:
                self._backup(source)
            if self._witness is not None:
                mark_recovery_ready(self.workspace)
            for staged, destination in replacement_assets:
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
        mark_workspace_committed(self.workspace)
        finalize_workspace(self.album_dir, self.workspace)

    def discard(self) -> None:
        with suppress(FileNotFoundError):
            shutil.rmtree(self.workspace)
