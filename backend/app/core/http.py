"""Shared HTTP client factory with caching, retries, and rate limiting.

hishel's FilterPolicy caches ALL responses by default (including 429s/500s).
This module provides a factory that builds cached httpx clients which only
cache successful (2xx) responses.
"""

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from hishel import (
    AsyncSqliteStorage,
    BaseFilter,
    FilterPolicy,
    Response as HishelResponse,
)
from hishel.httpx import AsyncCacheTransport
from httpx import AsyncBaseTransport, AsyncClient, AsyncHTTPTransport, Request, Response
from httpx_retries import Retry, RetryTransport

if TYPE_CHECKING:
    from aiolimiter import AsyncLimiter

from app.core.config import get_settings

_CACHE_TTL = 60 * 60 * 24 * 30  # 30 days


class _CacheOnlySuccess(BaseFilter[HishelResponse]):
    def needs_body(self) -> bool:
        return False

    def apply(self, item: HishelResponse, body: bytes | None) -> bool:  # noqa: ARG002
        return 200 <= item.status_code < 300


class RateLimitedTransport(AsyncBaseTransport):
    """Rate-limits and caps concurrency on cache miss only.

    Semaphore is acquired first so rate-limit tokens are only consumed
    when the request is ready to send (no wasted tokens on queue wait).
    """

    def __init__(
        self,
        limiter: AsyncLimiter,
        *,
        max_concurrent: int = 10,
        weight_fn: Callable[[Request], int] = lambda _: 1,
    ) -> None:
        self._transport = AsyncHTTPTransport()
        self._limiter = limiter
        self._sem = asyncio.Semaphore(max_concurrent)
        self._weight_fn = weight_fn

    async def handle_async_request(self, request: Request) -> Response:
        async with self._sem:
            await self._limiter.acquire(self._weight_fn(request))
            return await self._transport.handle_async_request(request)


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
    policy: FilterPolicy[HishelResponse] = FilterPolicy(
        response_filters=[_CacheOnlySuccess()]
    )
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
