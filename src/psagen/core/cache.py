# pyright: basic

from __future__ import annotations

import functools
import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, overload

import diskcache

from psagen.core.client import APIClient
from psagen.core.logger import get_logger
from psagen.core.settings import settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine, Iterator


logger = get_logger(__name__)

# Global cache instance with SQLite backend
_cache: diskcache.Cache | None = None


def get_cache() -> diskcache.Cache:
    """Get or create the global cache instance."""
    global _cache  # noqa: PLW0603
    if _cache is None:
        settings.cache_dir.mkdir(parents=True, exist_ok=True)
        _cache = diskcache.Cache(str(settings.cache_dir))
    return _cache


_cache_tries = [0]
_cache_hits = [0]


def log_cache_stats() -> None:
    logger.info(
        "Cache stats: %d/%d/%d: %d%% hits",
        _cache_tries[0],
        _cache_hits[0],
        _cache_tries[0] - _cache_hits[0],
        100 * _cache_hits[0] / _cache_tries[0],
    )


_NOT_HASHABLE = APIClient


def _make_cache_key[**P, R](func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> str:
    hashable_args = [arg for arg in args if not isinstance(arg, _NOT_HASHABLE)]
    hashable_kwarg = {k: v for k, v in kwargs.items() if not isinstance(v, _NOT_HASHABLE)}
    return f"{func.__qualname__}:{hashable_args}:{hashable_kwarg}"


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
        key = _make_cache_key(func, *args, **kwargs)

        if not _force_update.get():
            _cache_tries[0] += 1
            cached: T | None = cache.get(key, default=None)  # pyright: ignore[reportAssignmentType]
            if cached is not None:
                _cache_hits[0] += 1
                return cached
            logger.info("Cache miss: %s", key)

        # Call original function
        result: T = await func(*args, **kwargs)  # pyright: ignore[reportGeneralTypeIssues]

        # Store in cache
        cache.set(key, result)
        return result

    @functools.wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        cache = get_cache()
        key = _make_cache_key(func, *args, **kwargs)

        if not _force_update.get():
            _cache_tries[0] += 1
            cached: T | None = cache.get(key, default=None)  # pyright: ignore[reportAssignmentType]
            if cached is not None:
                _cache_hits[0] += 1
                return cached
            logger.info("Cache miss: %s", key)

        # Call original function
        result: T = func(*args, **kwargs)  # pyright: ignore[reportAssignmentType]

        # Store in cache
        cache.set(key, result)
        return result

    return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
