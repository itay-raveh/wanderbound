"""HTTP client for Open Meteo APIs.

Both endpoints (archive-api / api) share an IP-based rate limit, so they
use one limiter.  Rate limiting sits between the cache and network layers
so cache hits bypass it.  Cache keys are URL-based (unique query params).
"""

from aiolimiter import AsyncLimiter
from httpx import AsyncBaseTransport, AsyncHTTPTransport, Request, Response

from app.core.http import cached_client


class _RateLimitedTransport(AsyncBaseTransport):
    """Rate-limits on cache miss only.

    For the elevation API each coordinate in the batch counts as one call,
    so the weight is derived from the comma-separated ``latitude`` param.
    """

    def __init__(self, limiter: AsyncLimiter) -> None:
        self._transport = AsyncHTTPTransport()
        self._limiter = limiter

    async def handle_async_request(self, request: Request) -> Response:
        weight = 1
        lat = request.url.params.get("latitude", "")
        if "," in lat:
            weight = lat.count(",") + 1
        await self._limiter.acquire(weight)
        return await self._transport.handle_async_request(request)


# Free tier: 600 calls/min, 5 000/hr.  We stay under with 480/min.
_limiter = AsyncLimiter(480, 60)

_client = cached_client(transport=_RateLimitedTransport(limiter=_limiter))


async def get(url: str, *, params: dict) -> Response:
    return await _client.get(url, params=params)
