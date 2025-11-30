"""Data caching utilities using diskcache."""

import asyncio
from typing import Any

from diskcache import Cache

from src.core.logger import get_logger
from src.core.settings import settings

logger = get_logger(__name__)

settings.file.cache_dir.mkdir(parents=True, exist_ok=True)
_cache = Cache(str(settings.file.cache_dir))


async def get_cached(key: str) -> Any | None:
    """Get value from persistent cache asynchronously."""
    try:
        return await asyncio.to_thread(_cache.get, key)
    except Exception as e:  # noqa: BLE001
        logger.warning("Cache read error for key %s: %s", key, e)
        return None


async def set_cached(key: str, value: Any, expire: int | None = None) -> None:
    """Set value in persistent cache asynchronously."""
    try:
        await asyncio.to_thread(_cache.set, key, value, expire=expire)
    except Exception as e:  # noqa: BLE001
        logger.warning("Cache write error for key %s: %s", key, e)


async def clear_cache() -> None:
    """Clear the persistent cache."""
    try:
        await asyncio.to_thread(_cache.clear)
        logger.info("Cache cleared")
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to clear cache: %s", e)
