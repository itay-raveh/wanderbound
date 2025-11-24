"""Caching utilities for API responses."""

from pathlib import Path
from typing import Any

import diskcache

from ..logger import get_logger

logger = get_logger(__name__)

CACHE_DIR = Path.home() / ".cache" / "polarsteps-album-generator"
CACHE_DIR.mkdir(exist_ok=True)

# Create diskcache instance with LRU eviction policy
_cache = diskcache.Cache(
    str(CACHE_DIR), size_limit=2**30, eviction_policy="least-recently-used"
)


def get_cached(key: str) -> Any | None:
    """Get cached API response."""
    try:
        return _cache.get(key, default=None)
    except Exception as e:
        logger.debug(f"Error getting cached value for key '{key}': {e}")
        return None


def set_cached(key: str, value: Any) -> None:
    """Cache API response."""
    try:
        _cache.set(key, value)
    except Exception as e:
        logger.debug(f"Error setting cached value for key '{key}': {e}")
