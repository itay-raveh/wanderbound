"""HTTP caching utilities using hishel."""

import hishel
import httpx

from src.core.settings import settings


def get_cache_controller() -> hishel.Controller:
    """Get a hishel cache controller with standard configuration."""
    return hishel.Controller(
        cacheable_methods=["GET"],
        cacheable_status_codes=[200],
        allow_stale=True,
        always_revalidate=False,
    )


def get_cache_storage() -> hishel.AsyncFileStorage:
    """Get a hishel file storage backend."""
    http_cache_dir = settings.file.cache_dir / "http_cache"
    http_cache_dir.mkdir(parents=True, exist_ok=True)
    return hishel.AsyncFileStorage(base_path=http_cache_dir, ttl=60 * 60 * 24 * 30)  # 30 days TTL


def create_cached_client(
    limits: httpx.Limits | None = None, timeout: float = 30.0
) -> hishel.AsyncCacheClient:
    """Create a hishel AsyncCacheClient with file storage."""
    if limits is None:
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)

    storage = get_cache_storage()
    controller = get_cache_controller()

    return hishel.AsyncCacheClient(
        storage=storage,
        controller=controller,
        limits=limits,
        timeout=timeout,
    )
