from collections.abc import Callable
from itertools import pairwise

import httpx
import pytest

from app.models.segment import RouteEnrichmentStatus
from app.services.mapbox import (
    REQUEST_BUDGET_EXCEEDED,
    MapboxRouteClients,
    MapboxTransientError,
    _fetch_directions,
    _fetch_matching,
    _match_one,
    _RequestBudget,
    route_request_batch_indices,
)

type Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _timed(coords: list[tuple[float, float]]) -> list[tuple[float, float, float]]:
    return [
        (lon, lat, 1_700_000_000.267 + i * 60) for i, (lon, lat) in enumerate(coords)
    ]


async def test_map_matching_no_match_is_terminal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["timestamps"] == "1700000000;1700000060"
        return httpx.Response(200, json={"code": "NoMatch"}, request=request)

    async with _client(handler) as client:
        result = await _fetch_matching(
            client,
            _timed([(4.0, 52.0), (4.1, 52.1)]),
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
                _timed([(4.0, 52.0), (4.1, 52.1)]),
                "driving",
                "token",
            )


async def test_mapbox_invalid_input_is_recorded_as_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"code": "InvalidInput"}, request=request)

    async with _client(handler) as client:
        result = await _fetch_directions(
            client,
            _timed([(4.0, 52.0), (4.1, 52.1)]),
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
            _timed([(4.0, 52.0), (4.1, 52.1)]),
            "driving",
            "token",
        )

    assert result.status == RouteEnrichmentStatus.no_route
    assert result.error_code == "NoSegment"


async def test_chunked_matching_rejects_partial_success() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            return httpx.Response(
                422,
                json={"code": "NoSegment"},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "matchings": [
                    {
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[0.0, 0.0], [0.001, 0.0]],
                        }
                    }
                ],
            },
            request=request,
        )

    points = _timed([(i * 0.001, 0.0) for i in range(101)])
    async with _client(handler) as client:
        result = await _match_one(
            MapboxRouteClients(matching=client, directions=client),
            points,
            "driving",
            "token",
        )

    assert calls == 2
    assert result.status == RouteEnrichmentStatus.no_route
    assert result.route is None
    assert result.error_code == "NoSegment"


async def test_chunked_matching_stitches_at_the_shared_point() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        encoded = request.url.path.rsplit("/", 1)[-1]
        coords = [
            [float(value) for value in pair.split(",")] for pair in encoded.split(";")
        ]
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "matchings": [
                    {
                        "geometry": {
                            "type": "LineString",
                            "coordinates": coords,
                        }
                    }
                ],
            },
            request=request,
        )

    points = _timed([(i * 0.001, 0.01 * (i % 2)) for i in range(101)])
    async with _client(handler) as client:
        result = await _match_one(
            MapboxRouteClients(matching=client, directions=client),
            points,
            "driving",
            "token",
        )

    assert calls == 2
    assert result.status == RouteEnrichmentStatus.matched
    assert result.route is not None
    assert all(
        current[0] < following[0] for current, following in pairwise(result.route)
    )


async def test_request_budget_falls_back_without_calling_mapbox() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    async with _client(handler) as client:
        result = await _match_one(
            MapboxRouteClients(matching=client, directions=client),
            _timed([(4.0, 52.0), (4.001, 52.001)]),
            "walking",
            "token",
            budget=_RequestBudget(0),
        )

    assert calls == 0
    assert result.status == RouteEnrichmentStatus.no_route
    assert result.error_code == REQUEST_BUDGET_EXCEEDED


def test_route_request_batch_uses_remaining_capacity() -> None:
    short_route = _timed([(4.0, 52.0), (4.001, 52.001)])
    chunked_route = _timed([(i * 0.001, 0.0) for i in range(101)])

    indexes = route_request_batch_indices(
        [
            (short_route, "walking"),
            (chunked_route, "driving"),
            (short_route, "walking"),
        ],
        max_requests=2,
    )

    assert indexes == [0, 2]
