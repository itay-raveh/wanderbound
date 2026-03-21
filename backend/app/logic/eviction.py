import asyncio
import logging
import shutil
from pathlib import Path

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import engine
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
    Only deletes filesystem data — DB records are preserved.
    """
    users_folder = settings.USERS_FOLDER
    cap = settings.MAX_STORAGE_BYTES

    total, sizes = await asyncio.to_thread(_sizes_by_user, users_folder)
    if total <= cap:
        return

    logger.info(
        "Storage %d MB exceeds cap %d MB, starting eviction",
        total // 1_048_576,
        cap // 1_048_576,
    )

    async with AsyncSession(engine) as session:
        result = await session.exec(
            select(User).order_by(User.last_active_at.asc())  # type: ignore[union-attr]
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
        logger.info("Evicted user %d folder (%d MB)", user.id, folder_size // 1_048_576)

    logger.info("Eviction complete, storage now %d MB", total // 1_048_576)
