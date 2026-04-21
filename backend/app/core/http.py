"""Shared HTTP client factory with caching, retries, and rate limiting.

hishel's FilterPolicy caches ALL responses by default (including 429s/500s).
This module's factory builds cached httpx clients that only cache successful
(2xx) responses.

Timeout enforcement: hishel converts httpx requests to an internal format,
stripping the timeout extensions. The underlying network transport never
sees the client-level timeout and can block indefinitely. All transports
built here enforce an explicit ``asyncio.timeout`` to compensate.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

import httpx
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
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_DEFAULT_LIMITS = httpx.Limits(max_connections=20)


class _CacheOnlySuccess(BaseFilter[HishelResponse]):
    def needs_body(self) -> bool:
        return False

    def apply(self, item: HishelResponse, body: bytes | None) -> bool:  # noqa: ARG002
        return 200 <= item.status_code < 300


class _TimeoutTransport(AsyncBaseTransport):
    """Wraps AsyncHTTPTransport with an explicit asyncio.timeout deadline.

    Re-raises asyncio.TimeoutError as httpx.ReadTimeout so that
    RetryTransport (which only retries httpx.TimeoutException subclasses)
    can retry the request.
    """

    def __init__(self, timeout: float, limits: httpx.Limits) -> None:
        self._timeout = timeout
        self._transport = AsyncHTTPTransport(limits=limits)

    async def handle_async_request(self, request: Request) -> Response:
        try:
            async with asyncio.timeout(self._timeout):
                return await self._transport.handle_async_request(request)
        except TimeoutError as exc:
            raise ReadTimeout(
                f"Request to {request.url.host} timed out after {self._timeout}s"
            ) from exc


class RateLimitedTransport(AsyncBaseTransport):
    """Rate-limits requests on cache miss.

    Connection-pool concurrency is capped by ``httpx.Limits`` on the
    underlying transport. This wrapper only enforces a token-bucket
    rate, not parallelism.
    """

    def __init__(
        self,
        inner: AsyncBaseTransport,
        limiter: AsyncLimiter,
        *,
        weight_fn: Callable[[Request], int] = lambda _: 1,
    ) -> None:
        self._inner = inner
        self._limiter = limiter
        self._weight_fn = weight_fn

    async def handle_async_request(self, request: Request) -> Response:
        await self._limiter.acquire(self._weight_fn(request))
        return await self._inner.handle_async_request(request)


_RETRY = Retry(total=3, backoff_factor=0.5, status_forcelist=_RETRY_STATUS_CODES)


def http_client(  # noqa: PLR0913
    *,
    cache: bool = True,
    use_body_key: bool = False,
    limiter: AsyncLimiter | None = None,
    weight_fn: Callable[[Request], int] | None = None,
    limits: httpx.Limits = _DEFAULT_LIMITS,
    follow_redirects: bool = False,
    timeout: float = 30.0,
) -> AsyncClient:
    """Build an httpx AsyncClient with retries, optional cache, and optional rate limit.

    The transport chain is: ``[Cache ->] Retry -> [RateLimit ->] Timeout -> network``.

    ``cache`` wraps in hishel's SQLite cache (2xx only, 30-day TTL).
    ``use_body_key`` includes request body in cache key (POST-based APIs).
    ``limiter`` is an AsyncLimiter applied on cache miss, weighted by ``weight_fn``.
    ``limits`` caps connection-pool concurrency. ``timeout`` enforces a per-request
    deadline (applies even when hishel strips httpx timeouts).
    """
    transport: AsyncBaseTransport = _TimeoutTransport(timeout, limits)
    if limiter is not None:
        transport = RateLimitedTransport(
            transport, limiter, weight_fn=weight_fn or (lambda _: 1)
        )
    transport = RetryTransport(transport=transport, retry=_RETRY)

    if cache:
        policy: FilterPolicy[HishelResponse] = FilterPolicy(
            response_filters=[_CacheOnlySuccess()]
        )
        if use_body_key:
            policy.use_body_key = True
        transport = AsyncCacheTransport(
            transport,
            storage=AsyncSqliteStorage(
                default_ttl=_CACHE_TTL,
                database_path=get_settings().DATA_FOLDER / "http_cache.sqlite",
            ),  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
            policy=policy,
        )

    return AsyncClient(
        transport=transport,
        follow_redirects=follow_redirects,
        timeout=timeout,
    )
