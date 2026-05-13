from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from sqlmodel import select

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.worker_threads import run_sync
from app.logic.layout.media import Media, delete_thumbnails, is_video
from app.models.album import Album
from app.models.album_media import AlbumMedia, AlbumMediaUndoSnapshot

UNDO_DIR = ".undo"
UNDO_TTL = timedelta(minutes=5)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


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
    album_dir: Path,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
    rows = (
        await session.exec(
            select(AlbumMediaUndoSnapshot).where(
                AlbumMediaUndoSnapshot.expires_at <= _as_utc(now)
            )
        )
    ).all()
    for row in rows:
        await run_sync((album_dir / row.snapshot_path).unlink, missing_ok=True)
        await session.delete(row)
    await session.flush()
    return len(rows)
