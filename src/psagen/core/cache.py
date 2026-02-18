# ruff: noqa: ANN401
# pyright: reportAny=false,reportExplicitAny=false
from __future__ import annotations

import functools
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from diskcache.core import Cache, args_to_key, full_name

from psagen.core.client import APIClient
from psagen.core.logger import get_logger
from psagen.core.settings import settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator


logger = get_logger(__name__)

# Global cache instance with SQLite backend
settings.cache_dir.mkdir(parents=True, exist_ok=True)
_cache = Cache(str(settings.cache_dir))
_cache.stats(enable=True)


def log_cache_stats() -> None:
    hits, misses = _cache.stats()
    if hits + misses:
        logger.info(
            "Cache stats: %d/%d/%d: %d%% hits",
            hits + misses,
            hits,
            misses,
            100 * hits / (hits + misses),
        )


_NOT_HASHABLE = (APIClient,)


def _is_arg_ok(arg: Any) -> bool:
    return not isinstance(arg, _NOT_HASHABLE) and not callable(arg)


def _make_cache_key[**P, R](
    func: Callable[P, R], *args: P.args, **kwargs: P.kwargs
) -> tuple[str, ...]:
    clean_args = tuple(str(arg) for arg in args if _is_arg_ok(arg))
    clean_kw = {k: str(v) for k, v in kwargs.items() if _is_arg_ok(v)}
    return args_to_key((full_name(func),), clean_args, clean_kw, typed=False, ignore=set())


_force_update: ContextVar[bool] = ContextVar("force_update", default=False)


@contextmanager
def force_cache_update() -> Iterator[None]:
    """Context manager to force cache updates (skip read, always write)."""
    token = _force_update.set(True)
    try:
        yield
    finally:
        _force_update.reset(token)


def async_cache[**P, T](func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        key = _make_cache_key(func, *args, **kwargs)

        if not _force_update.get():
            try:
                return _cache[key]
            except KeyError:
                logger.info("Cache miss: %s", key)

        result: T = await func(*args, **kwargs)
        _cache[key] = result
        return result

    return wrapper
