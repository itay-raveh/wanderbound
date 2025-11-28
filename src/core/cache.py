"""Data caching utilities using diskcache."""

from typing import Any

from diskcache import Cache

from src.core.logger import get_logger
from src.core.settings import settings

logger = get_logger(__name__)

DATA_CACHE_DIR = settings.file.cache_dir / "data_cache"
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_cache = Cache(str(DATA_CACHE_DIR))


def get_cached(key: str) -> Any | None:
    """Get value from persistent cache."""
    try:
        return _cache.get(key)
    except Exception as e:  # noqa: BLE001
        logger.warning("Cache read error for key %s: %s", key, e)
        return None


def set_cached(key: str, value: Any, expire: int | None = None) -> None:
    """Set value in persistent cache."""
    try:
        _cache.set(key, value, expire=expire)
    except Exception as e:  # noqa: BLE001
        logger.warning("Cache write error for key %s: %s", key, e)
