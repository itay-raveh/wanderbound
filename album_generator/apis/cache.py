"""Caching utilities for API responses."""

from pathlib import Path
from typing import Optional, Any, List
import diskcache
from more_itertools import chunked

CACHE_DIR = Path.home() / ".polarsteps_album_cache"
CACHE_DIR.mkdir(exist_ok=True)

# Create diskcache instance with 24-hour TTL
_cache = diskcache.Cache(str(CACHE_DIR), size_limit=2**30, eviction_policy="least-recently-used")


def get_cached(key: str) -> Optional[Any]:
    """Get cached API response."""
    try:
        return _cache.get(key, default=None)
    except Exception:
        return None


def set_cached(key: str, value: Any):
    """Cache API response."""
    try:
        _cache.set(key, value, expire=86400)
    except Exception:
        pass


def _get_elevation_cache() -> diskcache.Cache:
    """Get elevation-specific cache instance."""
    elevation_cache_dir = CACHE_DIR / "elevation"
    elevation_cache_dir.mkdir(exist_ok=True)
    return diskcache.Cache(str(elevation_cache_dir), size_limit=2**30)
