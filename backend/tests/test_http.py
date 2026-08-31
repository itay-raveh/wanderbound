import time

import httpx
import pytest
from pyrate_limiter import Rate

from app.core.http import RateLimitedTransport, sliding_window_limiter


class _RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.requests: list[float] = []
        self.closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(time.monotonic())
        return httpx.Response(200, request=request)

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.unit
async def test_rate_limited_transport_enforces_weighted_rolling_window() -> None:
    inner = _RecordingTransport()
    transport = RateLimitedTransport(
        inner,
        sliding_window_limiter(Rate(3, 100), Rate(4, 300)),
        weight_fn=lambda _: 2,
    )
    request = httpx.Request("GET", "https://example.com")

    await transport.handle_async_request(request)
    await transport.handle_async_request(request)
    await transport.handle_async_request(request)
    await transport.aclose()

    assert inner.requests[1] - inner.requests[0] >= 0.1
    assert inner.requests[2] - inner.requests[0] >= 0.3
    assert inner.closed
