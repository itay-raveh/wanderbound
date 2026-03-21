"""Shared HTTP client factory with caching and retries.

hishel's FilterPolicy caches ALL responses by default (including 429s/500s).
This module provides a factory that builds cached httpx clients which only
cache successful (2xx) responses.
"""

from hishel import AsyncSqliteStorage, BaseFilter, FilterPolicy, Response
from hishel.httpx import AsyncCacheTransport
from httpx import AsyncBaseTransport, AsyncClient
from httpx_retries import Retry, RetryTransport

from app.core.config import get_settings

_CACHE_TTL = 60 * 60 * 24 * 30  # 30 days


class _CacheOnlySuccess(BaseFilter[Response]):
    def needs_body(self) -> bool:
        return False

    def apply(self, item: Response, body: bytes | None) -> bool:  # noqa: ARG002
        return 200 <= item.status_code < 300


def cached_client(
    *,
    transport: AsyncBaseTransport | None = None,
    use_body_key: bool = False,
) -> AsyncClient:
    """Build an httpx AsyncClient with SQLite caching, retries, and optional middleware.

    Only 2xx responses are cached. Cached entries live for 30 days.
    Retries are always included. The chain is: Cache -> Retry -> transport -> network.

    Args:
        transport: Optional inner transport (e.g. rate-limiting layer).
        use_body_key: Include request body in cache key (for POST requests).
    """
    policy = FilterPolicy(response_filters=[_CacheOnlySuccess()])
    if use_body_key:
        policy.use_body_key = True

    return AsyncClient(
        transport=AsyncCacheTransport(
            RetryTransport(
                transport=transport, retry=Retry(total=3, backoff_factor=0.5)
            ),
            storage=AsyncSqliteStorage(
                default_ttl=_CACHE_TTL,
                database_path=get_settings().DATA_FOLDER / "http_cache.sqlite",
            ),  # type: ignore[arg-type]
            policy=policy,
        )
    )
