"""Postgres advisory locks for cross-request (and cross-worker) mutual exclusion.

Session-scoped: held until the dedicated connection closes, so safe to wrap
long-running SSE streams. Auto-released if the process dies - no TTL sweep,
no stale entries. Use for "only one of this operation per resource at a time"
semantics. For in-process concurrency caps, reach for asyncio primitives.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy_dlock import create_async_sadlock

from app.core.db import get_engine


@asynccontextmanager
async def try_advisory_lock(key: str) -> AsyncIterator[bool]:
    """Yield True if the lock was acquired, False if it's held elsewhere.

    The connection is held for the full duration of the context, counting
    against the engine pool (size=10, max_overflow=10). Callers should
    release the lock quickly or scale the pool accordingly.
    """
    async with get_engine().connect() as conn:
        lock = create_async_sadlock(conn, key)
        acquired = await lock.acquire(block=False)
        try:
            yield acquired
        finally:
            if acquired:
                await lock.release()
