from __future__ import annotations

import asyncio
import contextlib
import shutil
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

from app.core.db import get_engine
from app.core.worker_threads import run_sync
from app.logic.external_media.files import (
    CleanupAction,
    MediaAssetTransition,
    OperationWitness,
    PendingMediaOperation,
    finalize_workspace,
    mark_recovery_ready,
    mark_workspace_committed,
    rebase_workspace_path,
    recover_workspace,
    recovery_witness,
    recovery_workspaces,
    register_workspace,
    run_best_effort_cleanup,
    sweep_pending_workspaces,
    write_recovery_manifest,
)
from app.logic.layout.media import Media, delete_thumbnails, extract_frame, is_video
from app.logic.panorama.storage import panorama_original_path
from app.models.album import Album
from app.models.album_media import AlbumMedia, AlbumMediaUndoSnapshot
from app.models.user import User

UNDO_DIR = ".undo"
UNDO_TTL = timedelta(minutes=5)
UNDO_CLEANUP_INTERVAL = 60.0

logger = structlog.get_logger(__name__)
_undo_prune_tasks: set[asyncio.Task[None]] = set()


@asynccontextmanager
async def lifespan() -> AsyncGenerator[None]:
    await _prune_all_expired_undo_snapshots_once(recover_all_pending=True)
    task = asyncio.create_task(_prune_all_expired_undo_snapshots_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _video_poster(path: Path) -> Path:
    return path.with_suffix(".jpg")


def undo_snapshot_path(album_dir: Path, stored_path: str) -> Path:
    candidate = (album_dir / stored_path).resolve()
    undo_dir = (album_dir / UNDO_DIR).resolve()
    try:
        relative = candidate.relative_to(undo_dir)
    except ValueError as error:
        raise ValueError("Undo snapshot path must remain beneath .undo") from error
    if not relative.parts:
        raise ValueError("Undo snapshot path must name a file beneath .undo")
    return candidate


def _require_readable_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} missing or unreadable")
    try:
        with path.open("rb") as source:
            source.read(1)
    except OSError as error:
        raise ValueError(f"{label} missing or unreadable") from error


def _discard_tree(path: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(path)


async def _unlink_snapshot(album_dir: Path, row: AlbumMediaUndoSnapshot) -> None:
    path = undo_snapshot_path(album_dir, row.snapshot_path)
    original = (
        undo_snapshot_path(album_dir, row.original_snapshot_path)
        if row.original_snapshot_path
        else None
    )
    await run_sync(path.unlink, missing_ok=True)
    if is_video(path.name):
        await run_sync(_video_poster(path).unlink, missing_ok=True)
    if original is not None:
        await run_sync(original.unlink, missing_ok=True)


class UndoSnapshotUpdate:
    def __init__(
        self,
        snapshot: AlbumMediaUndoSnapshot,
        workspace: Path,
        previous_values: dict[str, object] | None,
        witness: OperationWitness,
    ) -> None:
        self.snapshot = snapshot
        self.album_dir = workspace.parents[2]
        self.workspace = workspace
        self.activated: list[tuple[Path, Path]] = []
        self.previous: list[tuple[Path, Path]] = []
        self.previous_values = previous_values
        self.witness = witness

    def prepare_recovery(
        self,
        undo_dir: Path,
        previous_paths: list[Path],
        staged_moves: list[tuple[Path, Path]],
    ) -> None:
        write_recovery_manifest(
            self.album_dir,
            self.workspace,
            self.witness,
            [
                (
                    self.workspace / "previous" / current.relative_to(undo_dir),
                    current,
                )
                for current in previous_paths
                if current.exists()
            ],
            [(destination, staged) for staged, destination in staged_moves],
        )

    def rollback_activated(self) -> None:
        for destination, staged in reversed(self.activated):
            if destination.exists():
                staged.parent.mkdir(parents=True, exist_ok=True)
                destination.replace(staged)
        self.activated.clear()

    def rollback_previous(self) -> None:
        for backup, original in reversed(self.previous):
            if backup.exists():
                original.parent.mkdir(parents=True, exist_ok=True)
                backup.replace(original)
        self.previous.clear()

    def rollback_values(self) -> None:
        if self.previous_values is not None:
            for name, value in self.previous_values.items():
                setattr(self.snapshot, name, value)

    def rollback(self) -> None:
        self.rollback_activated()
        self.rollback_previous()
        self.rollback_values()
        self.discard()

    async def rollback_best_effort(self) -> None:
        await run_best_effort_cleanup(
            "external_media.undo_snapshot_compensation_failed",
            ("activated", partial(run_sync, self.rollback_activated)),
            ("previous", partial(run_sync, self.rollback_previous)),
            ("row", partial(run_sync, self.rollback_values)),
            ("workspace", partial(run_sync, self.discard)),
        )

    def register_cleanup(self) -> None:
        previous_workspace = self.workspace
        self.workspace = register_workspace(self.album_dir, self.workspace)
        self.activated = [
            (
                destination,
                rebase_workspace_path(staged, previous_workspace, self.workspace),
            )
            for destination, staged in self.activated
        ]
        self.previous = [
            (
                rebase_workspace_path(backup, previous_workspace, self.workspace),
                original,
            )
            for backup, original in self.previous
        ]

    def finish(self) -> None:
        mark_workspace_committed(self.workspace)
        finalize_workspace(self.album_dir, self.workspace)

    def discard(self) -> None:
        _discard_tree(self.workspace)


@dataclass(frozen=True)
class StagedUndoAssets:
    workspace: Path
    moves: list[tuple[Path, Path]]
    original_snapshot_path: str | None


async def _stage_undo_assets(
    *,
    source: Path,
    undo_dir: Path,
    media_name: str,
    row: AlbumMedia | None,
) -> StagedUndoAssets:
    workspace = undo_dir / ".staging" / uuid.uuid4().hex
    moves: list[tuple[Path, Path]] = []
    original_snapshot_path: str | None = None
    try:
        staged_primary = workspace / "new" / media_name
        await run_sync(staged_primary.parent.mkdir, parents=True, exist_ok=True)
        await run_sync(shutil.copy2, source, staged_primary)
        moves.append((staged_primary, undo_dir / media_name))

        source_poster = _video_poster(source)
        if is_video(media_name) and source_poster.exists():
            staged_poster = _video_poster(staged_primary)
            await run_sync(shutil.copy2, source_poster, staged_poster)
            moves.append((staged_poster, _video_poster(undo_dir / media_name)))

        original = panorama_original_path(
            undo_dir.parent,
            row.panorama.original_path if row and row.panorama else None,
        )
        if original is not None and original.exists():
            staged_original = workspace / "new" / "panorama-originals" / original.name
            snapshot_original = undo_dir / "panorama-originals" / original.name
            await run_sync(staged_original.parent.mkdir, parents=True, exist_ok=True)
            await run_sync(shutil.copy2, original, staged_original)
            moves.append((staged_original, snapshot_original))
            original_snapshot_path = str(snapshot_original.relative_to(undo_dir.parent))
    except BaseException:
        await run_sync(_discard_tree, workspace)
        raise
    return StagedUndoAssets(workspace, moves, original_snapshot_path)


def _snapshot_values(snapshot: AlbumMediaUndoSnapshot) -> dict[str, object]:
    return {
        "snapshot_path": snapshot.snapshot_path,
        "perceptual_hashes": snapshot.perceptual_hashes,
        "panorama": snapshot.panorama,
        "original_snapshot_path": snapshot.original_snapshot_path,
        "upgrade_candidate": snapshot.upgrade_candidate,
        "created_at": snapshot.created_at,
        "expires_at": snapshot.expires_at,
    }


def _snapshot_paths(
    album_dir: Path,
    media_name: str,
    existing: AlbumMediaUndoSnapshot | None,
    staged: StagedUndoAssets,
) -> list[Path]:
    paths: list[Path] = []
    if existing is not None:
        primary = undo_snapshot_path(album_dir, existing.snapshot_path)
        paths.append(primary)
        if is_video(media_name):
            paths.append(_video_poster(primary))
        if existing.original_snapshot_path:
            paths.append(undo_snapshot_path(album_dir, existing.original_snapshot_path))
    paths.extend(destination for _, destination in staged.moves)
    return list(dict.fromkeys(paths))


def _activate_snapshot_update(
    update: UndoSnapshotUpdate,
    undo_dir: Path,
    previous_paths: list[Path],
    staged_moves: list[tuple[Path, Path]],
) -> None:
    update.prepare_recovery(undo_dir, previous_paths, staged_moves)
    for current in previous_paths:
        if current.exists():
            backup = update.workspace / "previous" / current.relative_to(undo_dir)
            backup.parent.mkdir(parents=True, exist_ok=True)
            current.replace(backup)
            update.previous.append((backup, current))
    mark_recovery_ready(update.workspace)
    for staged, destination in staged_moves:
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(destination)
        update.activated.append((destination, staged))


@dataclass(frozen=True)
class PreparedUndoRestore:
    snapshot: Path
    media: Media
    original: tuple[Path, Path] | None


async def _prepare_undo_restore(
    album_dir: Path,
    media_name: str,
    snapshot: AlbumMediaUndoSnapshot,
) -> PreparedUndoRestore:
    snapshot_path = undo_snapshot_path(album_dir, snapshot.snapshot_path)
    await run_sync(_require_readable_file, snapshot_path, "Undo snapshot")

    replacement_original = None
    if snapshot.original_snapshot_path is not None:
        original_snapshot = undo_snapshot_path(
            album_dir, snapshot.original_snapshot_path
        )
        await run_sync(
            _require_readable_file,
            original_snapshot,
            "Panorama original snapshot",
        )
        active_original = panorama_original_path(
            album_dir,
            snapshot.panorama.original_path if snapshot.panorama else None,
        )
        if active_original is None:
            raise ValueError("Panorama original snapshot is invalid")
        replacement_original = (original_snapshot, active_original)

    if is_video(media_name):
        snapshot_poster = _video_poster(snapshot_path)
        if not snapshot_poster.exists():
            await extract_frame(snapshot_path)
        await run_sync(_require_readable_file, snapshot_poster, "Undo snapshot poster")
        restored = await Media.probe(snapshot_path)
    else:
        restored = await run_sync(Media.load, snapshot_path)
    return PreparedUndoRestore(snapshot_path, restored, replacement_original)


def _restore_row_values(
    row: AlbumMedia,
    prepared: PreparedUndoRestore,
    snapshot: AlbumMediaUndoSnapshot,
    target: Path,
) -> None:
    row.width = prepared.media.width
    row.height = prepared.media.height
    row.byte_size = target.stat().st_size
    row.perceptual_hashes = snapshot.perceptual_hashes
    row.panorama = snapshot.panorama
    row.upgrade_candidate = snapshot.upgrade_candidate
    row.updated_at = datetime.now(UTC)


def _reset_row_values(row: AlbumMedia, values: dict[str, object]) -> None:
    for name, value in values.items():
        setattr(row, name, value)


def enqueue_undo_snapshot_prune(
    background_tasks: BackgroundTasks,
    uid: int,
    aid: str,
    album_dir: Path,
) -> None:
    background_tasks.add_task(schedule_undo_snapshot_prune, uid, aid, album_dir)


async def schedule_undo_snapshot_prune(
    uid: int,
    aid: str,
    album_dir: Path,
    delay: float = UNDO_TTL.total_seconds(),
) -> None:
    asyncio.get_running_loop().call_later(
        delay,
        _start_undo_snapshot_prune_task,
        uid,
        aid,
        album_dir,
    )


def _start_undo_snapshot_prune_task(uid: int, aid: str, album_dir: Path) -> None:
    task = asyncio.create_task(_prune_expired_undo_snapshots_task(uid, aid, album_dir))
    _undo_prune_tasks.add(task)
    task.add_done_callback(_undo_prune_tasks.discard)


async def _prune_expired_undo_snapshots_task(
    uid: int,
    aid: str,
    album_dir: Path,
) -> None:
    try:
        async with AsyncSession(get_engine(), expire_on_commit=False) as session:
            removed = await prune_expired_undo_snapshots(
                session,
                uid=uid,
                aid=aid,
                album_dir=album_dir,
            )
            await session.commit()
        if removed:
            logger.info(
                "external_media.undo_pruned",
                user_id=uid,
                album_id=aid,
                count=removed,
            )
    except SQLAlchemyError, OSError:
        logger.debug(
            "external_media.undo_prune_failed",
            user_id=uid,
            album_id=aid,
            exc_info=True,
        )


async def create_undo_snapshot(
    session: AsyncSession,
    *,
    uid: int,
    aid: str,
    album_dir: Path,
    media_name: str,
) -> UndoSnapshotUpdate | None:
    source = album_dir / media_name
    if not source.exists():
        return None
    undo_dir = album_dir / UNDO_DIR
    await run_sync(undo_dir.mkdir, parents=True, exist_ok=True)
    now = datetime.now(UTC)
    await prune_expired_undo_snapshots(
        session,
        uid=uid,
        aid=aid,
        album_dir=album_dir,
        now=now,
    )
    row = await session.get(AlbumMedia, (uid, aid, media_name))
    existing = await session.get(AlbumMediaUndoSnapshot, (uid, aid, media_name))
    staged = await _stage_undo_assets(
        source=source,
        undo_dir=undo_dir,
        media_name=media_name,
        row=row,
    )

    previous_values: dict[str, object] | None = None
    if existing is None:
        snap = AlbumMediaUndoSnapshot(
            uid=uid,
            aid=aid,
            media_name=media_name,
            snapshot_path=str(Path(UNDO_DIR) / media_name),
            perceptual_hashes=row.perceptual_hashes if row else None,
            panorama=row.panorama if row else None,
            original_snapshot_path=staged.original_snapshot_path,
            upgrade_candidate=row.upgrade_candidate if row else True,
            created_at=now,
            expires_at=now + UNDO_TTL,
        )
    else:
        snap = existing
        previous_values = _snapshot_values(snap)

    try:
        previous_paths = _snapshot_paths(album_dir, media_name, existing, staged)
    except BaseException:
        await run_sync(_discard_tree, staged.workspace)
        raise
    update = UndoSnapshotUpdate(
        snap,
        staged.workspace,
        previous_values,
        OperationWitness(uid, aid, media_name, now),
    )
    try:
        await run_sync(
            _activate_snapshot_update,
            update,
            undo_dir,
            previous_paths,
            staged.moves,
        )

        snap.snapshot_path = str(Path(UNDO_DIR) / media_name)
        snap.perceptual_hashes = row.perceptual_hashes if row else None
        snap.panorama = row.panorama if row else None
        snap.original_snapshot_path = staged.original_snapshot_path
        snap.upgrade_candidate = row.upgrade_candidate if row else True
        snap.created_at = now
        snap.expires_at = now + UNDO_TTL
        session.add(snap)
        await run_sync(update.register_cleanup)
        await session.flush()
    except BaseException:
        await update.rollback_best_effort()
        raise
    return update


async def restore_undo_snapshot(
    session: AsyncSession,
    *,
    album: Album,
    album_dir: Path,
    media_name: str,
) -> PendingMediaOperation[AlbumMedia]:
    row = await session.get_one(
        AlbumMedia,
        (album.uid, album.id, media_name),
        with_for_update=True,
    )
    snap = await session.get(AlbumMediaUndoSnapshot, (album.uid, album.id, media_name))
    if snap is None:
        raise ValueError("No undo snapshot available")
    if _as_utc(snap.expires_at) <= datetime.now(UTC):
        raise ValueError("Undo snapshot expired")

    prepared = await _prepare_undo_restore(album_dir, media_name, snap)
    target = album_dir / media_name
    transition = MediaAssetTransition(album_dir, media_name)
    transition.set_recovery_witness(
        OperationWitness(album.uid, album.id, media_name, None)
    )
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
        await run_sync(
            transition.activate,
            prepared.snapshot,
            row.panorama,
            replacement_original=prepared.original,
        )
        await run_sync(delete_thumbnails, target)
        _restore_row_values(row, prepared, snap, target)
        session.add(row)
        await run_sync(transition.register_cleanup)
        await session.delete(snap)
        await session.flush()
    except BaseException:
        compensations: tuple[CleanupAction, ...] = (
            ("media_transition", partial(run_sync, transition.rollback)),
            ("media_row", partial(run_sync, _reset_row_values, row, previous_values)),
        )
        await run_best_effort_cleanup(
            "external_media.undo_compensation_failed",
            *compensations,
        )
        raise
    else:
        return PendingMediaOperation(
            result=row,
            rollback_actions=(
                ("media_transition", partial(run_sync, transition.rollback)),
                (
                    "media_row",
                    partial(run_sync, _reset_row_values, row, previous_values),
                ),
            ),
            finalizers=(("media_transition", partial(run_sync, transition.finish)),),
        )


async def prune_expired_undo_snapshots(
    session: AsyncSession,
    *,
    uid: int,
    aid: str,
    album_dir: Path,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
    await recover_pending_workspaces(session, album_dir, now - UNDO_TTL)
    await run_sync(sweep_pending_workspaces, album_dir, now - UNDO_TTL)
    rows = (
        await session.exec(
            select(AlbumMediaUndoSnapshot).where(
                AlbumMediaUndoSnapshot.uid == uid,
                AlbumMediaUndoSnapshot.aid == aid,
                AlbumMediaUndoSnapshot.expires_at <= _as_utc(now),
            )
        )
    ).all()
    for row in rows:
        await _unlink_snapshot(album_dir, row)
        await session.delete(row)
    await session.flush()
    return len(rows)


async def prune_all_expired_undo_snapshots(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    recover_all_pending: bool = False,
) -> int:
    now = now or datetime.now(UTC)
    albums = (await session.exec(select(Album))).all()
    recovery_cutoff = (
        datetime.max.replace(tzinfo=UTC) if recover_all_pending else now - UNDO_TTL
    )
    for album in albums:
        user = await session.get(User, album.uid)
        if user is not None:
            album_dir = user.trips_folder / album.id
            await recover_pending_workspaces(session, album_dir, recovery_cutoff)
            await run_sync(sweep_pending_workspaces, album_dir, now - UNDO_TTL)
    rows = (
        await session.exec(
            select(AlbumMediaUndoSnapshot).where(
                AlbumMediaUndoSnapshot.expires_at <= _as_utc(now)
            )
        )
    ).all()
    removed = 0
    for row in rows:
        user = await session.get(User, row.uid)
        if user is not None:
            album_dir = user.trips_folder / row.aid
            await _unlink_snapshot(album_dir, row)
        await session.delete(row)
        removed += 1
    await session.flush()
    return removed


async def recover_pending_workspaces(
    session: AsyncSession,
    album_dir: Path,
    cutoff: datetime,
) -> None:
    workspaces = await run_sync(recovery_workspaces, album_dir, cutoff)
    for workspace in workspaces:
        try:
            witness = await run_sync(recovery_witness, workspace)
            if witness is None:
                continue
            snapshot = await session.get(
                AlbumMediaUndoSnapshot,
                (witness.uid, witness.aid, witness.media_name),
            )
            committed = (
                snapshot is None
                if witness.snapshot_created_at is None
                else snapshot is not None
                and _as_utc(snapshot.created_at) == _as_utc(witness.snapshot_created_at)
            )
            await run_sync(
                recover_workspace,
                album_dir,
                workspace,
                committed=committed,
            )
        except OSError, TypeError, ValueError:
            logger.warning(
                "external_media.pending_recovery_failed",
                workspace=str(workspace),
                exc_info=True,
            )


async def _prune_all_expired_undo_snapshots_once(
    *,
    recover_all_pending: bool = False,
) -> None:
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        removed = await prune_all_expired_undo_snapshots(
            session,
            recover_all_pending=recover_all_pending,
        )
        await session.commit()
    if removed:
        logger.info("external_media.undo_pruned", count=removed)


async def _prune_all_expired_undo_snapshots_loop() -> None:
    while True:
        await asyncio.sleep(UNDO_CLEANUP_INTERVAL)
        try:
            await _prune_all_expired_undo_snapshots_once()
        except SQLAlchemyError, OSError:
            logger.debug("external_media.undo_prune_failed", exc_info=True)
