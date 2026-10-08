import asyncio
from collections.abc import Awaitable, Callable
from itertools import pairwise

import httpx
import pytest

from app.models.segment import RouteEnrichmentStatus
from app.services.mapbox import (
    MATCH_CHUNK_COORDS,
    REQUEST_BUDGET_EXCEEDED,
    ROUTE_REQUEST_BATCH_TARGET,
    MapboxRouteClients,
    MapboxTransientError,
    RouteMatchStats,
    _fetch_directions,
    _fetch_matching,
    _match_one,
    _RequestBudget,
    route_request_batch_indices,
)

type Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


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


async def test_map_matching_preserves_subsecond_endpoint() -> None:
    points = [
        (4.0, 52.0, 1_700_000_000.1),
        (4.1, 52.1, 1_700_000_001.1),
        (4.2, 52.2, 1_700_000_001.9),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/4.0,52.0;4.1,52.1;4.2,52.2")
        assert request.url.params["timestamps"] == ("1700000000;1700000001;1700000001")
        return httpx.Response(200, json={"code": "NoMatch"}, request=request)

    async with _client(handler) as client:
        result = await _fetch_matching(client, points, "walking", "token")

    assert result.status == RouteEnrichmentStatus.no_route


async def test_mapbox_server_failure_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"code": "ServerError", "message": "Service unavailable"},
            request=request,
        )

    async with _client(handler) as client:
        with pytest.raises(
            MapboxTransientError,
            match="directions:ServerError: Service unavailable",
        ):
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
                "tracepoints": [{"matchings_index": 0}]
                * len(request.url.path.rsplit("/", 1)[-1].split(";")),
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


async def test_chunked_matching_cancels_sibling_after_transport_failure() -> None:
    started = 0
    cancelled = 0
    both_started = asyncio.Event()
    never_finishes = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal cancelled, started
        started += 1
        if started == 2:
            both_started.set()
        async with asyncio.timeout(1):
            await both_started.wait()

        encoded = request.url.path.rsplit("/", 1)[-1]
        if encoded.startswith("4.0,52.0;"):
            raise httpx.ConnectError("injected", request=request)
        try:
            await never_finishes.wait()
        except asyncio.CancelledError:
            cancelled += 1
            raise
        raise AssertionError("unreachable")

    points = _timed([(4.0 + i * 0.001, 52.0) for i in range(101)])
    async with _client(handler) as client:
        with pytest.raises(MapboxTransientError):
            await _match_one(
                MapboxRouteClients(matching=client, directions=client),
                points,
                "driving",
                "token",
            )

    assert started == 2
    assert cancelled == 1


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
                "tracepoints": [{"matchings_index": 0}]
                * len(request.url.path.rsplit("/", 1)[-1].split(";")),
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


async def test_single_route_exceeds_target_with_bounded_execution() -> None:
    point_count = 2 + ROUTE_REQUEST_BATCH_TARGET * (MATCH_CHUNK_COORDS - 1)
    oversized_route = _timed([(4.0 + i * 0.00001, 52.0) for i in range(point_count)])
    calls = 0
    active = 0
    peak_active = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, calls, peak_active
        calls += 1
        active += 1
        peak_active = max(peak_active, active)
        try:
            await asyncio.sleep(0)
        finally:
            active -= 1
        encoded = request.url.path.rsplit("/", 1)[-1]
        pairs = encoded.split(";")
        coords = [
            [float(value) for value in pair.split(",")]
            for pair in (pairs[0], pairs[-1])
        ]
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "tracepoints": [{"matchings_index": 0}]
                * len(request.url.path.rsplit("/", 1)[-1].split(";")),
                "matchings": [
                    {"geometry": {"type": "LineString", "coordinates": coords}}
                ],
            },
            request=request,
        )

    indexes = route_request_batch_indices([(oversized_route, "driving")])
    async with _client(handler) as client:
        result = await _match_one(
            MapboxRouteClients(matching=client, directions=client),
            oversized_route,
            "driving",
            "token",
            budget=_RequestBudget(ROUTE_REQUEST_BATCH_TARGET),
        )

    assert indexes == [0]
    assert calls > ROUTE_REQUEST_BATCH_TARGET
    assert peak_active <= ROUTE_REQUEST_BATCH_TARGET
    assert result.status == RouteEnrichmentStatus.matched


@pytest.mark.parametrize("shape", ["prefix", "suffix", "split", "no_match", "outlier"])
async def test_sparse_trace_keeps_complete_route_coverage(
    shape: str,
) -> None:
    points = [(4.0, 52.0, 0.0), (4.1, 52.05, 3 * 3600.0), (4.2, 52.1, 3 * 3600.0 + 60)]
    route = [[4.0, 52.0], [4.08, 52.08], [4.1, 52.05], [4.2, 52.1]]
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "/directions/" in request.url.path:
            assert request.url.path.endswith("/4.0,52.0;4.1,52.05;4.2,52.1")
            return httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "routes": [
                        {"geometry": {"type": "LineString", "coordinates": route}}
                    ],
                },
                request=request,
            )
        geometry = {
            "type": "LineString",
            "coordinates": route if shape == "outlier" else route[1:],
        }
        tracepoints: list[dict[str, int] | None] = [{"matchings_index": 0}] * 3
        matchings = [{"geometry": geometry}]
        if shape == "outlier":
            tracepoints[1] = None
        elif shape == "prefix":
            tracepoints[0] = None
        elif shape == "suffix":
            tracepoints[-1] = None
        elif shape == "split":
            matchings.append({"geometry": geometry})
        data = (
            {"code": "NoMatch"}
            if shape == "no_match"
            else {
                "code": "Ok",
                "matchings": matchings,
                "tracepoints": tracepoints,
            }
        )
        return httpx.Response(
            200, json=data, request=request, extensions={"hishel_from_cache": True}
        )

    stats = RouteMatchStats()
    async with _client(handler) as client:
        result = await _match_one(
            MapboxRouteClients(client, client), points, "driving", "token", stats
        )
    assert result.status == RouteEnrichmentStatus.matched
    assert result.route == [tuple(coord) for coord in route]
    assert len(requests) == (1 if shape == "outlier" else 2)
    assert stats.matching_requests == stats.cache_hits == 1
    assert stats.directions_requests == (0 if shape == "outlier" else 1)


async def test_unroutable_sparse_trace_keeps_gps_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        code = "NoMatch" if "/matching/" in request.url.path else "NoRoute"
        return httpx.Response(200, json={"code": code}, request=request)

    async with _client(handler) as client:
        result = await _match_one(
            MapboxRouteClients(client, client),
            _timed([(4.0, 52.0), (4.1, 52.1), (4.2, 52.2)]),
            "driving",
            "token",
        )
    assert result.status == RouteEnrichmentStatus.no_route
    assert result.route is None
    assert result.error_code == "NoRoute"


async def test_partial_match_fallback_respects_coordinate_and_request_limits() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "/matching/" in request.url.path:
            return httpx.Response(200, json={"code": "NoMatch"}, request=request)
        coords = [
            [float(v) for v in pair.split(",")]
            for pair in request.url.path.rsplit("/", 1)[-1].split(";")
        ]
        assert len(coords) <= 25
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "routes": [{"geometry": {"type": "LineString", "coordinates": coords}}],
            },
            request=request,
        )

    points = _timed([(4.0 + i * 0.001, 52.0 + (i % 2) * 0.001) for i in range(90)])
    assert route_request_batch_indices([(points, "driving")] * 3, max_requests=4) == [
        0,
        1,
    ]
    async with _client(handler) as client:
        result = await _match_one(
            MapboxRouteClients(client, client),
            points,
            "driving",
            "token",
            budget=_RequestBudget(2),
        )
    assert len(calls) == 2
    assert result.status == RouteEnrichmentStatus.matched
    assert result.route
    assert result.route[0] == points[0][:2]
    assert result.route[-1] == points[-1][:2]


async def test_discontinuous_trace_never_requests_matching_or_directions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("discontinuous traces must not be routed")

    async with _client(handler) as client:
        result = await _match_one(
            MapboxRouteClients(client, client),
            [(4.0, 52.0, 0.0), (4.1, 52.1, 4 * 3600.0), (4.2, 52.2, 4 * 3600.0 + 60)],
            "driving",
            "token",
        )
    assert result.status == RouteEnrichmentStatus.no_route
    assert result.error_code == "discontinuous_trace"
