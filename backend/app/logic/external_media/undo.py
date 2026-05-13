from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime, timedelta
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
from app.logic.layout.media import Media, delete_thumbnails, extract_frame, is_video
from app.models.album import Album
from app.models.album_media import AlbumMedia, AlbumMediaUndoSnapshot

UNDO_DIR = ".undo"
UNDO_TTL = timedelta(minutes=5)

logger = structlog.get_logger(__name__)
_undo_prune_tasks: set[asyncio.Task[None]] = set()


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


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
) -> AlbumMediaUndoSnapshot | None:
    source = album_dir / media_name
    if not source.exists():
        return None
    undo_dir = album_dir / UNDO_DIR
    await run_sync(undo_dir.mkdir, parents=True, exist_ok=True)
    snapshot_path = undo_dir / media_name
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
    if existing is not None:
        await run_sync((album_dir / existing.snapshot_path).unlink, missing_ok=True)
        await session.delete(existing)
        await session.flush()
    await run_sync(shutil.copy2, source, snapshot_path)
    snap = AlbumMediaUndoSnapshot(
        uid=uid,
        aid=aid,
        media_name=media_name,
        snapshot_path=str(Path(UNDO_DIR) / media_name),
        upgrade_candidate=row.upgrade_candidate if row else True,
        created_at=now,
        expires_at=now + UNDO_TTL,
    )
    session.add(snap)
    await session.flush()
    return snap


async def restore_undo_snapshot(
    session: AsyncSession,
    *,
    album: Album,
    album_dir: Path,
    media_name: str,
) -> AlbumMedia:
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

    snapshot_path = album_dir / snap.snapshot_path
    if not snapshot_path.exists():
        raise ValueError("Undo snapshot missing")

    target = album_dir / media_name
    await run_sync(shutil.move, snapshot_path, target)
    await run_sync(delete_thumbnails, target)
    if is_video(media_name):
        await extract_frame(target)
    restored = (
        await Media.probe(target)
        if is_video(media_name)
        else await run_sync(Media.load, target)
    )
    row.width = restored.width
    row.height = restored.height
    row.byte_size = target.stat().st_size
    row.upgrade_candidate = snap.upgrade_candidate
    row.updated_at = datetime.now(UTC)
    session.add(row)
    await session.delete(snap)
    await session.flush()
    return row


async def prune_expired_undo_snapshots(
    session: AsyncSession,
    *,
    uid: int,
    aid: str,
    album_dir: Path,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
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
        await run_sync((album_dir / row.snapshot_path).unlink, missing_ok=True)
        await session.delete(row)
    await session.flush()
    return len(rows)
