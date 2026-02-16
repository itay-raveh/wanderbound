# pyright: basic

from __future__ import annotations

import functools
import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, overload

import diskcache

from psagen.core.settings import settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine, Iterator


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
    # noinspection PyUnresolvedReferences
    return f"{func.__module__}.{func.__qualname__}:{normalized_args}:{normalized_kwargs}"


_force_update: ContextVar[bool] = ContextVar("force_update", default=False)


@contextmanager
def force_cache_update() -> Iterator[None]:
    """Context manager to force cache updates (skip read, always write)."""
    token = _force_update.set(True)
    try:
        yield
    finally:
        _force_update.reset(token)


@overload
def async_cache[**P, Y, S, R](
    func: Callable[P, Coroutine[Y, S, R]],
) -> Callable[P, Coroutine[Y, S, R]]: ...


@overload
def async_cache[**P, T](func: Callable[P, T]) -> Callable[P, T]: ...


def async_cache[**P, T](
    func: Callable[P, T] | Callable[P, Awaitable[T]],
) -> Callable[P, T | Awaitable[T]]:
    @functools.wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        cache = get_cache()
        key = _make_cache_key(func, args, kwargs)

        if not _force_update.get():
            cached: T | None = cache.get(key, default=None)  # pyright: ignore[reportAssignmentType]
            if cached is not None:
                return cached

        # Call original function
        result: T = await func(*args, **kwargs)  # pyright: ignore[reportGeneralTypeIssues]

        # Store in cache
        cache.set(key, result)
        return result

    @functools.wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        cache = get_cache()
        key = _make_cache_key(func, args, kwargs)

        if not _force_update.get():
            cached: T | None = cache.get(key, default=None)  # pyright: ignore[reportAssignmentType]
            if cached is not None:
                return cached

        # Call original function
        result: T = func(*args, **kwargs)  # pyright: ignore[reportAssignmentType]

        # Store in cache
        cache.set(key, result)
        return result

    return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
