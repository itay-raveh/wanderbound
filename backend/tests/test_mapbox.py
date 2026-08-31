from collections.abc import Callable

import httpx
import pytest

from app.models.segment import RouteEnrichmentStatus
from app.services.mapbox import (
    MapboxTransientError,
    RouteMatchResult,
    _chunked_route,
    _fetch_directions,
    _fetch_matching,
)

type Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_map_matching_no_match_is_terminal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "NoMatch"}, request=request)

    async with _client(handler) as client:
        result = await _fetch_matching(
            client,
            [(4.0, 52.0), (4.1, 52.1)],
            "walking",
            "token",
        )

    assert result.status == RouteEnrichmentStatus.no_route
    assert result.error_code == "NoMatch"


async def test_mapbox_server_failure_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"code": "ServerError"}, request=request)

    async with _client(handler) as client:
        with pytest.raises(MapboxTransientError, match="ServerError"):
            await _fetch_directions(
                client,
                [(4.0, 52.0), (4.1, 52.1)],
                "driving",
                "token",
            )


async def test_mapbox_invalid_input_is_recorded_as_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"code": "InvalidInput"}, request=request)

    async with _client(handler) as client:
        result = await _fetch_directions(
            client,
            [(4.0, 52.0), (4.1, 52.1)],
            "driving",
            "token",
        )

    assert result.status == RouteEnrichmentStatus.failed
    assert result.error_code == "InvalidInput"


async def test_mapbox_no_segment_response_is_terminal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"code": "NoSegment"}, request=request)

    async with _client(handler) as client:
        result = await _fetch_directions(
            client,
            [(4.0, 52.0), (4.1, 52.1)],
            "driving",
            "token",
        )

    assert result.status == RouteEnrichmentStatus.no_route
    assert result.error_code == "NoSegment"


async def test_chunked_route_rejects_partial_success() -> None:
    calls = 0

    async def route_chunk(
        chunk: list[tuple[float, float]],
    ) -> RouteMatchResult:
        nonlocal calls
        calls += 1
        if calls == 2:
            return RouteMatchResult(
                status=RouteEnrichmentStatus.no_route,
                error_code="NoSegment",
            )
        return RouteMatchResult(
            status=RouteEnrichmentStatus.matched,
            route=chunk,
        )

    result = await _chunked_route(
        [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0), (3.0, 3.0)],
        chunk_size=3,
        overlap=1,
        route_fn=route_chunk,
    )

    assert calls == 2
    assert result.status == RouteEnrichmentStatus.no_route
    assert result.route is None
    assert result.error_code == "NoSegment"
