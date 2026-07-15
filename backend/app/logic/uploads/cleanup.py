import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.logic.uploads.files import remove_tree_if_present
from app.models.processing import UploadSession
from app.services.upload_store import UploadStoreService

logger = structlog.get_logger(__name__)


async def cleanup_upload_sessions(
    session: AsyncSession,
    store: UploadStoreService,
    work_root: Path,
    *,
    now: datetime | None = None,
) -> None:
    current = now or datetime.now(UTC)
    expired = (
        await session.exec(
            select(UploadSession).where(
                col(UploadSession.status) == "uploading",
                col(UploadSession.expires_at) <= current,
            )
        )
    ).all()
    for row in expired:
        try:
            await asyncio.to_thread(store.abort, row.object_key, row.provider_upload_id)
        except Exception:
            logger.exception("upload.expiry_cleanup_failed", upload_id=row.upload_id)
            continue
        row.status = "aborted"
        row.completed_at = current
        row.updated_at = current
        session.add(row)

    old = (
        await session.exec(
            select(UploadSession).where(
                col(UploadSession.completed_at) < current - timedelta(days=7)
            )
        )
    ).all()
    for row in old:
        await session.delete(row)
        await asyncio.to_thread(remove_tree_if_present, work_root / row.upload_id)
    await session.commit()


async def upload_cleanup_loop(
    store: UploadStoreService, work_root: Path, *, interval_seconds: float = 300
) -> None:
    while True:
        try:
            async with AsyncSession(get_engine()) as session:
                await cleanup_upload_sessions(session, store, work_root)
        except Exception:
            logger.exception("upload.cleanup_loop_failed")
        await asyncio.sleep(interval_seconds)
