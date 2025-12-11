import shutil
from collections.abc import Callable
from typing import Any, TypeVar

from persist_cache import cache  # type: ignore[attr-defined]

from src.core.settings import settings

settings.cache_dir.mkdir(parents=True, exist_ok=True)

T = TypeVar("T", bound=Callable[..., Any])


def cache_in_file() -> Callable[[T], T]:
    """Decorator to cache function results using persist-cache."""
    return cache(dir=str(settings.cache_dir))


def clear_cache() -> None:
    """Clear the persistent cache."""
    if settings.cache_dir.exists():
        shutil.rmtree(settings.cache_dir)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
