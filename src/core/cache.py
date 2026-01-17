# pyright: basic

import shutil
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from persist_cache.persist_cache import cache

from src.core.settings import settings

settings.cache_dir.mkdir(parents=True, exist_ok=True)

P = ParamSpec("P")
T = TypeVar("T")


def cache_in_file() -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to cache function results using persist-cache."""
    return cache(dir=str(settings.cache_dir))


def clear_cache() -> None:
    """Clear the persistent cache."""
    if settings.cache_dir.exists():
        shutil.rmtree(settings.cache_dir)
