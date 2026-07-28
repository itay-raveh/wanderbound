from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlmodel import col, select

from app.core.config import get_settings
from app.core.locks import try_advisory_lock
from app.core.resources import MIN_DISK_FREE_BYTES
from app.logic.upload import MAX_ARCHIVE_UNCOMPRESSED_BYTES
from app.models.processing import UploadSession

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

_ADMISSION_LOCK = "upload-workspace-admission"


def has_upload_capacity(
    *,
    workspace_bytes: int,
    free_bytes: int,
    active_upload_sizes: list[int],
    new_upload_size: int,
) -> bool:
    reserved = sum(
        size + MAX_ARCHIVE_UNCOMPRESSED_BYTES for size in active_upload_sizes
    )
    requested = new_upload_size + MAX_ARCHIVE_UNCOMPRESSED_BYTES
    return reserved + requested <= workspace_bytes and requested <= free_bytes


@asynccontextmanager
async def upload_capacity_slot(
    session: AsyncSession, new_upload_size: int
) -> AsyncIterator[bool]:
    async with try_advisory_lock(_ADMISSION_LOCK) as acquired:
        if not acquired:
            yield False
            return
        statement = select(UploadSession.size_bytes).where(
            col(UploadSession.status).in_(("processing", "awaiting_selection"))
        )
        active_sizes = list(await session.exec(statement))
        settings = get_settings()
        usage = shutil.disk_usage(settings.DATA_FOLDER)
        yield has_upload_capacity(
            workspace_bytes=max(
                0,
                usage.total - settings.MAX_STORAGE_BYTES - MIN_DISK_FREE_BYTES,
            ),
            free_bytes=max(0, usage.free - MIN_DISK_FREE_BYTES),
            active_upload_sizes=active_sizes,
            new_upload_size=new_upload_size,
        )
