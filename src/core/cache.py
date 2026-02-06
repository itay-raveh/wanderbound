# pyright: basic
"""Async-compatible caching using diskcache with SQLite backend."""

from __future__ import annotations

import functools
import shutil
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, overload

import diskcache

from src.core.settings import settings

if TYPE_CHECKING:
    from collections.abc import Coroutine

P = ParamSpec("P")
T = TypeVar("T")

# Global cache instance with SQLite backend
_cache: diskcache.Cache | None = None


def get_cache() -> diskcache.Cache:
    """Get or create the global cache instance."""
    global _cache  # noqa: PLW0603
    if _cache is None:
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
        _cache = diskcache.Cache(str(settings.cache_dir))
    return _cache


def _make_cache_key(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Create a cache key from function name and arguments."""

    # Round coordinates to 2 decimal places (~1.1km precision) for location-based caching
    def normalize(v: Any) -> Any:
        if isinstance(v, float):
            return round(v, 2)
        return v

    normalized_args = tuple(normalize(a) for a in args)
    normalized_kwargs = {k: normalize(v) for k, v in sorted(kwargs.items())}
    return f"{func.__module__}.{func.__qualname__}:{normalized_args}:{normalized_kwargs}"


@overload
def async_cache(
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, T]]: ...


@overload
def async_cache(func: Callable[P, T]) -> Callable[P, T]: ...


def async_cache(func: Callable[P, T] | Callable[P, Awaitable[T]]) -> Callable[P, T | Awaitable[T]]:
    """Decorator for caching async function results using diskcache.

    Features:
    - Works with both sync and async functions
    - Coordinate rounding built-in (2 decimal places)
    - SQLite-backed for reliability
    - Respects global cache directory from settings

    Usage:
        @async_cache
        async def get_weather(lat: float, lon: float) -> WeatherData:
            ...
    """
    import asyncio  # noqa: PLC0415

    @functools.wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        cache = get_cache()
        key = _make_cache_key(func, args, kwargs)

        # Check cache only if not forced
        if not _force_update.get():
            cached = cache.get(key, default=None)
            if cached is not None:
                return cached  # type: ignore[return-value]

        # Call original function
        result = await func(*args, **kwargs)  # type: ignore[misc]

        # Store in cache
        cache.set(key, result)
        return result  # type: ignore[return-value]

    @functools.wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        cache = get_cache()
        key = _make_cache_key(func, args, kwargs)

        # Check cache only if not forced
        if not _force_update.get():
            cached = cache.get(key, default=None)
            if cached is not None:
                return cached  # type: ignore[return-value]

        # Call original function
        result = func(*args, **kwargs)

        # Store in cache
        cache.set(key, result)
        return result  # type: ignore[return-value]

    if asyncio.iscoroutinefunction(func):
        return async_wrapper  # type: ignore[return-value]
    return sync_wrapper  # type: ignore[return-value]


from contextlib import contextmanager
from contextvars import ContextVar

_force_update: ContextVar[bool] = ContextVar("force_update", default=False)


@contextmanager
def force_cache_update():
    """Context manager to force cache updates (skip read, always write)."""
    token = _force_update.set(True)
    try:
        yield
    finally:
        _force_update.reset(token)


def clear_cache() -> None:
    """Clear the persistent cache."""
    global _cache  # noqa: PLW0603
    if _cache is not None:
        _cache.close()
        _cache = None
    if settings.cache_dir.exists():
        shutil.rmtree(settings.cache_dir)
