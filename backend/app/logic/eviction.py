import asyncio
import shutil
from pathlib import Path

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.observability import set_span_data, start_span
from app.core.resources import MiB
from app.models.user import User

logger = structlog.get_logger(__name__)


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

    with start_span(
        "eviction.scan",
        "Scan storage for eviction",
        **{"app.workflow": "eviction", "user.id": skip_uid},
    ) as span:
        total, sizes = await asyncio.to_thread(_sizes_by_user, users_folder)
        set_span_data(
            span,
            **{
                "storage.used_bytes": total,
                "storage.limit_bytes": cap,
                "user.count": len(sizes),
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
            select(User).order_by(col(User.last_active_at).asc())
        )
        candidates = result.all()

    removed = 0
    with start_span(
        "eviction.delete",
        "Delete evicted user folders",
        **{
            "app.workflow": "eviction",
            "storage.used_bytes": total,
            "storage.limit_bytes": cap,
            "candidate.count": len(candidates),
        },
    ) as span:
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
            removed += 1
            logger.info(
                "eviction.user_removed",
                user_id=user.id,
                folder_size_mb=folder_size // MiB,
            )
        set_span_data(
            span,
            **{"user.removed": removed, "storage.remaining_bytes": total},
        )

    logger.info("eviction.completed", storage_mb=total // MiB)
