"""Shared HTTP client factory with caching, retries, and rate limiting.

hishel's FilterPolicy caches ALL responses by default (including 429s/500s).
This module provides a factory that builds cached httpx clients which only
cache successful (2xx) responses.

Timeout enforcement: hishel converts httpx requests to an internal format,
stripping the timeout extensions. The underlying network transport never
sees the client-level timeout and can block indefinitely. All transports
in this module enforce an explicit ``asyncio.timeout`` to compensate.
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
from httpx import (
    AsyncBaseTransport,
    AsyncClient,
    AsyncHTTPTransport,
    ReadTimeout,
    Request,
    Response,
)
from httpx_retries import Retry, RetryTransport

if TYPE_CHECKING:
    from aiolimiter import AsyncLimiter

from app.core.config import get_settings

_CACHE_TTL = 60 * 60 * 24 * 30  # 30 days
_NETWORK_TIMEOUT = 30  # seconds per individual request
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class _CacheOnlySuccess(BaseFilter[HishelResponse]):
    def needs_body(self) -> bool:
        return False

    def apply(self, item: HishelResponse, body: bytes | None) -> bool:  # noqa: ARG002
        return 200 <= item.status_code < 300


class _TimeoutTransport(AsyncBaseTransport):
    """Wraps AsyncHTTPTransport with an explicit asyncio.timeout.

    Re-raises asyncio.TimeoutError as httpx.ReadTimeout so that
    RetryTransport (which only retries httpx.TimeoutException subclasses)
    can retry the request.
    """

    def __init__(self) -> None:
        self._transport = AsyncHTTPTransport()

    async def handle_async_request(self, request: Request) -> Response:
        try:
            async with asyncio.timeout(_NETWORK_TIMEOUT):
                return await self._transport.handle_async_request(request)
        except TimeoutError as exc:
            raise ReadTimeout(
                f"Request to {request.url.host} timed out after {_NETWORK_TIMEOUT}s"
            ) from exc


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
        self._transport = _TimeoutTransport()
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
                transport=transport or _TimeoutTransport(),
                retry=Retry(
                    total=3,
                    backoff_factor=0.5,
                    status_forcelist=_RETRY_STATUS_CODES,
                ),
            ),
            storage=AsyncSqliteStorage(
                default_ttl=_CACHE_TTL,
                database_path=get_settings().DATA_FOLDER / "http_cache.sqlite",
            ),  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
            policy=policy,
        )
    )
