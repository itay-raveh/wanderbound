import asyncio
import shutil
from contextlib import suppress
from pathlib import Path

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.observability import set_span_data, start_span
from app.core.resources import MiB
from app.models.album import Album

logger = structlog.get_logger(__name__)


def _sizes_by_album(users_folder: Path) -> tuple[int, dict[tuple[int, str], int]]:
    if not users_folder.exists():
        return 0, {}
    by_album: dict[tuple[int, str], int] = {}
    for user_folder in users_folder.iterdir():
        try:
            uid = int(user_folder.name)
        except ValueError:
            continue
        trips_folder = user_folder / "trip"
        if not trips_folder.is_dir():
            continue
        for album_folder in trips_folder.iterdir():
            if album_folder.is_dir():
                by_album[(uid, album_folder.name)] = sum(
                    file.stat().st_size
                    for file in album_folder.rglob("*")
                    if file.is_file()
                )
    return sum(by_album.values()), by_album


def _remove_album(path: Path) -> None:
    with suppress(FileNotFoundError):
        shutil.rmtree(path)


async def run_eviction(skip_uid: int) -> None:
    """Delete LRU album media until total storage is under MAX_STORAGE_BYTES.

    Skips the user identified by skip_uid (the one who just uploaded).
    Database records and album edits are preserved.
    """
    s = get_settings()
    users_folder = s.USERS_FOLDER
    cap = s.MAX_STORAGE_BYTES

    with start_span(
        "eviction.scan",
        "Scan storage for eviction",
        **{"app.workflow": "eviction", "user.id": skip_uid},
    ) as span:
        total, sizes = await asyncio.to_thread(_sizes_by_album, users_folder)
        set_span_data(
            span,
            **{
                "storage.used_bytes": total,
                "storage.limit_bytes": cap,
                "album.count": len(sizes),
            },
        )
    if total <= cap:
        return

    logger.info(
        "eviction.started",
        storage_mb=total // MiB,
        cap_mb=cap // MiB,
    )

    async with AsyncSession(get_engine()) as session:
        result = await session.exec(
            select(Album).order_by(col(Album.last_active_at).asc())
        )
        candidates = result.all()

    removed = 0
    with start_span(
        "eviction.delete",
        "Delete evicted album media",
        **{
            "app.workflow": "eviction",
            "storage.used_bytes": total,
            "storage.limit_bytes": cap,
            "candidate.count": len(candidates),
        },
    ) as span:
        for album in candidates:
            if total <= cap:
                break
            if album.uid == skip_uid:
                continue
            key = (album.uid, album.id)
            folder_size = sizes.get(key, 0)
            if folder_size == 0:
                continue

            folder = users_folder / str(album.uid) / "trip" / album.id
            await asyncio.to_thread(_remove_album, folder)
            total -= folder_size
            removed += 1
            logger.info(
                "eviction.album_removed",
                user_id=album.uid,
                album_id=album.id,
                album_size_mb=folder_size // MiB,
            )
        set_span_data(
            span,
            **{"album.removed": removed, "storage.remaining_bytes": total},
        )

    logger.info("eviction.completed", storage_mb=total // MiB)
