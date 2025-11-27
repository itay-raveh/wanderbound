"""Caching utilities for API responses."""

from pathlib import Path
from typing import Any

import typed_diskcache as diskcache

from src.logger import get_logger

logger = get_logger(__name__)

CACHE_DIR = Path.home() / ".cache" / "polarsteps-album-generator"
CACHE_DIR.mkdir(exist_ok=True)

# Create diskcache instance with LRU eviction policy
_cache = diskcache.Cache(str(CACHE_DIR), size_limit=2**30, eviction_policy="least-recently-used")


# TODO(itay): Convert to async cache implementation


def get_cached(key: str) -> Any | None:
    """Get cached API response."""
    try:
        result = _cache.get(key, default=None)
        # typed_diskcache returns a cached value object with .value attribute
        # Handle case where key is not in cache (result is None)
        # Note: mypy may incorrectly flag this as unreachable due to typed_diskcache type stubs
    except (OSError, PermissionError, AttributeError) as e:
        logger.debug("Error getting cached value for key '%s': %s", key, e)
        return None
    except Exception as e:  # noqa: BLE001  # noqa: BLE001
        # Handle SQLAlchemy errors from typed_diskcache without importing sqlalchemy directly
        # (sqlalchemy is a transitive dependency via typed_diskcache)
        error_type_name = type(e).__name__
        if "CompileError" in error_type_name or "SQLAlchemyError" in error_type_name:
            logger.debug(
                "SQLAlchemy error getting cached value for key '%s': %s", key, error_type_name
            )
            return None
        # Catch any other unexpected exceptions
        logger.debug("Unexpected error getting cached value for key '%s': %s", key, error_type_name)
        return None
    else:
        if result is None:
            return None  # type: ignore[unreachable]
        return result.value


def set_cached(key: str, value: Any) -> None:
    """Cache API response."""
    try:
        _cache.set(key, value)
    except (OSError, PermissionError) as e:
        logger.debug("Error setting cached value for key '%s': %s", key, e)
    except Exception as e:  # noqa: BLE001  # noqa: BLE001
        # Handle SQLAlchemy errors from typed_diskcache without importing sqlalchemy directly
        # (sqlalchemy is a transitive dependency via typed_diskcache)
        error_type_name = type(e).__name__
        if "CompileError" in error_type_name or "SQLAlchemyError" in error_type_name:
            logger.debug(
                "SQLAlchemy error setting cached value for key '%s': %s", key, error_type_name
            )
        else:
            # Catch any other unexpected exceptions
            logger.debug(
                "Unexpected error setting cached value for key '%s': %s", key, error_type_name
            )
