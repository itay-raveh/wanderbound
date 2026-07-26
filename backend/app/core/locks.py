"""Mutual exclusion helpers for shared application resources.

Postgres advisory locks provide cross-request and cross-worker exclusion.
File generation locks coalesce duplicate work within one process.
"""

import asyncio
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy_dlock import create_async_sadlock

from app.core.db import get_engine

# Weak values keep waiter-held locks alive while collecting unused path entries.
_file_generation_locks: weakref.WeakValueDictionary[Path, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)


@asynccontextmanager
async def file_generation_lock(path: Path) -> AsyncIterator[None]:
    lock = _file_generation_locks.get(path)
    if lock is None:
        lock = asyncio.Lock()
        _file_generation_locks[path] = lock
    async with lock:
        yield


@asynccontextmanager
async def try_advisory_lock(key: str) -> AsyncIterator[bool]:
    """Yield True if the lock was acquired, False if it's held elsewhere.

    The connection is held for the full duration of the context, counting
    against the engine pool (size=10, max_overflow=10). Callers should
    release the lock quickly or scale the pool accordingly.
    """
    async with get_engine().connect() as raw_conn:
        conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
        lock = create_async_sadlock(conn, key)
        acquired = await lock.acquire(block=False)
        try:
            yield acquired
        finally:
            if acquired:
                await lock.release()
