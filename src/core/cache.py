import shutil
from collections.abc import Callable
from typing import Any, TypeVar, cast

from persist_cache import cache  # type: ignore[attr-defined]

from src.core.settings import settings

settings.file.cache_dir.mkdir(parents=True, exist_ok=True)

T = TypeVar("T", bound=Callable[..., Any])


def cache_result() -> Callable[[T], T]:
    """Decorator to cache function results using persist-cache."""
    return cast("Callable[[T], T]", cache(dir=str(settings.file.cache_dir)))


async def clear_cache() -> None:
    """Clear the persistent cache."""
    if settings.file.cache_dir.exists():
        shutil.rmtree(settings.file.cache_dir)
    settings.file.cache_dir.mkdir(parents=True, exist_ok=True)
