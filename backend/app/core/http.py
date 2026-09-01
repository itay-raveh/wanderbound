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
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter

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
from pyrate_limiter import BucketAsyncWrapper, InMemoryBucket, Limiter, Rate

from app.core.config import get_settings

_CACHE_TTL = 60 * 60 * 24 * 30  # 30 days
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_DEFAULT_LIMITS = httpx.Limits(max_connections=20)


@dataclass
class HttpTransportMetrics:
    outbound_attempts: int = 0
    limiter_wait_ms: int = 0
    provider_latency_ms: int = 0


_http_metrics: ContextVar[HttpTransportMetrics | None] = ContextVar(
    "http_transport_metrics", default=None
)


@contextmanager
def collect_http_transport_metrics() -> Iterator[HttpTransportMetrics]:
    metrics = HttpTransportMetrics()
    token = _http_metrics.set(metrics)
    try:
        yield metrics
    finally:
        _http_metrics.reset(token)


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

    async def aclose(self) -> None:
        await self._transport.aclose()


def sliding_window_limiter(*rates: Rate) -> Limiter:
    return Limiter(BucketAsyncWrapper(InMemoryBucket(list(rates))))


class RateLimitedTransport(AsyncBaseTransport):
    """Apply exact sliding-window limits to requests on cache miss.

    Connection-pool concurrency is capped by ``httpx.Limits`` on the
    underlying transport. This wrapper only enforces request windows.
    """

    def __init__(
        self,
        inner: AsyncBaseTransport,
        limiter: Limiter,
        *,
        weight_fn: Callable[[Request], int] = lambda _: 1,
    ) -> None:
        self._inner = inner
        self._limiter = limiter
        self._weight_fn = weight_fn

    async def handle_async_request(self, request: Request) -> Response:
        metrics = _http_metrics.get()
        wait_started = perf_counter()
        await self._limiter.try_acquire_async(
            "http-request", weight=self._weight_fn(request)
        )
        if metrics is not None:
            metrics.outbound_attempts += 1
            metrics.limiter_wait_ms += round((perf_counter() - wait_started) * 1000)
        provider_started = perf_counter()
        try:
            return await self._inner.handle_async_request(request)
        finally:
            if metrics is not None:
                metrics.provider_latency_ms += round(
                    (perf_counter() - provider_started) * 1000
                )

    async def aclose(self) -> None:
        try:
            await self._inner.aclose()
        finally:
            self._limiter.close()


def http_client(  # noqa: PLR0913
    *,
    cache: bool = True,
    use_body_key: bool = False,
    limiter: Limiter | None = None,
    weight_fn: Callable[[Request], int] | None = None,
    limits: httpx.Limits = _DEFAULT_LIMITS,
    follow_redirects: bool = False,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
    retry_allowed_methods: Iterable[str] | None = None,
) -> AsyncClient:
    """Build an httpx AsyncClient with retries, optional cache, and optional rate limit.

    The transport chain is: ``[Cache ->] Retry -> [RateLimit ->] Timeout -> network``.

    ``cache`` wraps in hishel's SQLite cache (2xx only, 30-day TTL).
    ``use_body_key`` includes request body in cache key (POST-based APIs).
    ``limiter`` applies exact sliding windows on cache miss, weighted by
    ``weight_fn``.
    ``limits`` caps connection-pool concurrency. ``timeout`` enforces a per-request
    deadline (applies even when hishel strips httpx timeouts).
    """
    transport: AsyncBaseTransport = _TimeoutTransport(timeout, limits)
    if limiter is not None:
        transport = RateLimitedTransport(
            transport, limiter, weight_fn=weight_fn or (lambda _: 1)
        )
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=_RETRY_STATUS_CODES,
        allowed_methods=retry_allowed_methods,
    )
    transport = RetryTransport(transport=transport, retry=retry)

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
        headers=headers,
    )
