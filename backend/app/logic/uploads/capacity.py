from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
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


@dataclass(frozen=True)
class StorageCapacity:
    total_bytes: int
    free_bytes: int
    persistent_budget_bytes: int
    minimum_free_bytes: int = MIN_DISK_FREE_BYTES


def has_upload_capacity(
    *,
    capacity: StorageCapacity,
    active_upload_sizes: list[int],
    new_upload_size: int,
) -> bool:
    workspace_budget = max(
        0,
        capacity.total_bytes
        - capacity.persistent_budget_bytes
        - capacity.minimum_free_bytes,
    )
    reserved = sum(
        size + MAX_ARCHIVE_UNCOMPRESSED_BYTES for size in active_upload_sizes
    )
    requested = new_upload_size + MAX_ARCHIVE_UNCOMPRESSED_BYTES
    return (
        reserved + requested <= workspace_budget
        and requested + capacity.minimum_free_bytes <= capacity.free_bytes
    )


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
            capacity=StorageCapacity(
                total_bytes=usage.total,
                free_bytes=usage.free,
                persistent_budget_bytes=settings.MAX_STORAGE_BYTES,
            ),
            active_upload_sizes=active_sizes,
            new_upload_size=new_upload_size,
        )
