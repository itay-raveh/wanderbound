import asyncio
import logging
import shutil
from pathlib import Path

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.resources import MiB
from app.models.user import User

logger = logging.getLogger(__name__)


def _sizes_by_user(users_folder: Path) -> tuple[int, dict[int, int]]:
    """Single-pass scan: total bytes and per-user-folder sizes."""
    if not users_folder.exists():
        return 0, {}
    by_user: dict[int, int] = {}
    for child in users_folder.iterdir():
        if child.is_dir():
            try:
                uid = int(child.name)
            except ValueError:
                continue
            size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
            by_user[uid] = size
    return sum(by_user.values()), by_user


async def run_eviction(skip_uid: int) -> None:
    """Delete LRU user folders until total storage is under MAX_STORAGE_BYTES.

    Skips the user identified by skip_uid (the one who just uploaded).
    Only deletes filesystem data - DB records are preserved.
    """
    s = get_settings()
    users_folder = s.USERS_FOLDER
    cap = s.MAX_STORAGE_BYTES

    total, sizes = await asyncio.to_thread(_sizes_by_user, users_folder)
    if total <= cap:
        return

    logger.info(
        "Storage %d MB exceeds cap %d MB, starting eviction",
        total // MiB,
        cap // MiB,
    )

    async with AsyncSession(get_engine()) as session:
        result = await session.exec(
            select(User).order_by(col(User.last_active_at).asc())
        )
        candidates = result.all()

    for user in candidates:
        if total <= cap:
            break
        if user.id == skip_uid:
            continue
        folder_size = sizes.get(user.id, 0)
        if folder_size == 0:
            continue

        await asyncio.to_thread(shutil.rmtree, user.folder, ignore_errors=True)
        total -= folder_size
        logger.info("Evicted user %d folder (%d MB)", user.id, folder_size // MiB)

    logger.info("Eviction complete, storage now %d MB", total // MiB)
