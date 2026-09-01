"""Mapbox routing for timestamped, contiguous GPS traces."""

import asyncio
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

import httpx
import structlog
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.http import collect_http_transport_metrics
from app.core.observability import set_span_data, start_span
from app.logic.route_matching import (
    Coords,
    reduce_coord_indices,
    simplify_route,
)
from app.logic.spatial.geo import total_length_km
from app.models.segment import RouteEnrichmentStatus

logger = structlog.get_logger(__name__)

type Profile = str  # "driving" or "walking"
type MapboxClient = httpx.AsyncClient
type TimedCoord = tuple[float, float, float]
type TimedCoords = list[TimedCoord]

MATCH_MAX_COORDS = 100
MATCH_CHUNK_COORDS = 90
MAX_ROUTE_REQUESTS_PER_RUN = 100
MAX_TRACE_GAP_S = 4 * 60 * 60
REQUEST_BUDGET_EXCEEDED = "request_budget_exceeded"

_DIRECTIONS_MAX_DISTANCE_KM = {"walking": 1_000.0, "driving": 10_000.0}

_MATCHING_URL = "https://api.mapbox.com/matching/v5/mapbox"
_DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox"


@dataclass
class RouteMatchStats:
    matching_requests: int = 0
    directions_requests: int = 0
    cache_hits: int = 0
    outbound_attempts: int = 0
    retries: int = 0
    limiter_wait_ms: int = 0
    provider_latency_ms: int = 0
    budget_fallbacks: int = 0

    @property
    def requests(self) -> int:
        return self.matching_requests + self.directions_requests


@dataclass(frozen=True)
class MapboxRouteClients:
    matching: MapboxClient
    directions: MapboxClient


@dataclass(frozen=True)
class _RoutePart:
    operation: Literal["matching", "directions"]
    points: TimedCoords


@dataclass
class _RequestBudget:
    remaining: int

    def reserve(self, requests: int) -> bool:
        if requests > self.remaining:
            return False
        self.remaining -= requests
        return True


class MapboxTransientError(RuntimeError):
    pass


class RouteMatchResult(BaseModel):
    status: RouteEnrichmentStatus
    route: Coords | None = None
    error_code: str | None = None


class _GeoJSONLineString(BaseModel):
    type: Literal["LineString"]
    coordinates: list[list[float]]


class _Matching(BaseModel):
    geometry: _GeoJSONLineString


class _MatchingResponse(BaseModel):
    code: str = "Ok"
    matchings: list[_Matching] = []


class _Route(BaseModel):
    geometry: _GeoJSONLineString


class _DirectionsResponse(BaseModel):
    code: str = "Ok"
    routes: list[_Route] = []


_NO_ROUTE_CODES = frozenset({"NoMatch", "NoRoute", "NoSegment"})


def _failed(error_code: str) -> RouteMatchResult:
    return RouteMatchResult(
        status=RouteEnrichmentStatus.failed,
        error_code=error_code[:100],
    )


def _no_route(error_code: str) -> RouteMatchResult:
    return RouteMatchResult(
        status=RouteEnrichmentStatus.no_route,
        error_code=error_code[:100],
    )


def _matched(route: Coords) -> RouteMatchResult:
    return RouteMatchResult(status=RouteEnrichmentStatus.matched, route=route)


def _response_error_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("code"), str):
        return payload["code"]
    return f"http_{response.status_code}"


def _http_failure(response: httpx.Response, *, operation: str) -> RouteMatchResult:
    error_code = _response_error_code(response)
    logger.warning(
        "mapbox.api_error",
        operation=operation,
        status_code=response.status_code,
        error_code=error_code,
    )
    if response.status_code == 429 or response.status_code >= 500:
        raise MapboxTransientError(f"{operation}:{error_code}")
    if error_code in _NO_ROUTE_CODES:
        return _no_route(error_code)
    return _failed(error_code)


def _encode_coords(coords: Coords) -> str:
    return ";".join(f"{lon},{lat}" for lon, lat in coords)


def _coords(points: TimedCoords) -> Coords:
    return [(lon, lat) for lon, lat, _ in points]


def _matching_request_points(points: TimedCoords) -> list[tuple[int, int]]:
    selected = reduce_coord_indices(_coords(points), MATCH_MAX_COORDS)
    request_points: list[tuple[int, int]] = []
    for index in selected:
        timestamp = int(points[index][2])
        if not request_points or timestamp > request_points[-1][1]:
            request_points.append((index, timestamp))
    return request_points


def _parse_matching_response(response: httpx.Response) -> RouteMatchResult:
    data = _MatchingResponse.model_validate_json(response.content)
    if data.code in _NO_ROUTE_CODES:
        return _no_route(data.code)
    if data.code != "Ok":
        return _failed(data.code)
    if not data.matchings:
        return _no_route("NoMatch")
    all_coords: Coords = []
    for matching in data.matchings:
        points: Coords = [
            (coord[0], coord[1]) for coord in matching.geometry.coordinates
        ]
        all_coords.extend(points[1:] if all_coords else points)
    return _matched(all_coords) if len(all_coords) >= 2 else _failed("invalid_geometry")


def _record_cache_result(
    response: httpx.Response, stats: RouteMatchStats | None
) -> None:
    if stats is not None and response.extensions.get("hishel_from_cache") is True:
        stats.cache_hits += 1


def _token() -> str | None:
    token = get_settings().MAPBOX_TOKEN
    if not token:
        logger.warning("mapbox.token_missing")
    return token


async def _fetch_matching(
    client: httpx.AsyncClient,
    points: TimedCoords,
    profile: Profile,
    token: str,
    stats: RouteMatchStats | None = None,
) -> RouteMatchResult:
    coords = _coords(points)
    request_points = _matching_request_points(points)
    if len(request_points) < 2:
        return _no_route("insufficient_timestamp_span")
    if stats is not None:
        stats.matching_requests += 1
    reduced = [coords[index] for index, _ in request_points]
    timestamps = [timestamp for _, timestamp in request_points]
    with start_span(
        "mapbox.matching",
        "Mapbox Map Matching API",
        **{
            "app.workflow": "route_enrichment",
            "route.profile": profile,
            "point.count": len(coords),
            "reduced_point.count": len(reduced),
        },
    ) as span:
        try:
            response = await client.get(
                f"{_MATCHING_URL}/{profile}/{_encode_coords(reduced)}",
                params={
                    "geometries": "geojson",
                    "overview": "full",
                    "tidy": "true",
                    "timestamps": ";".join(map(str, timestamps)),
                    "access_token": token,
                },
            )
            _record_cache_result(response, stats)
            set_span_data(span, **{"http.status_code": response.status_code})
        except httpx.RequestError as exc:
            logger.warning(
                "mapbox.matching_request_failed",
                error_type=type(exc).__name__,
            )
            raise MapboxTransientError("matching:request_failed") from exc
    if not response.is_success:
        return _http_failure(response, operation="matching")
    return _parse_matching_response(response)


async def _fetch_directions(
    client: httpx.AsyncClient,
    points: TimedCoords,
    profile: Profile,
    token: str,
    stats: RouteMatchStats | None = None,
) -> RouteMatchResult:
    if stats is not None:
        stats.directions_requests += 1
    coords = _coords(points)
    with start_span(
        "mapbox.directions",
        "Mapbox Directions API",
        **{
            "app.workflow": "route_enrichment",
            "route.profile": profile,
            "point.count": len(coords),
        },
    ) as span:
        try:
            response = await client.get(
                f"{_DIRECTIONS_URL}/{profile}/{_encode_coords(coords)}",
                params={
                    "geometries": "geojson",
                    "overview": "full",
                    "access_token": token,
                },
            )
            _record_cache_result(response, stats)
            set_span_data(span, **{"http.status_code": response.status_code})
        except httpx.RequestError as exc:
            logger.warning(
                "mapbox.directions_request_failed",
                error_type=type(exc).__name__,
            )
            raise MapboxTransientError("directions:request_failed") from exc
    if not response.is_success:
        return _http_failure(response, operation="directions")
    data = _DirectionsResponse.model_validate_json(response.content)
    if data.code in _NO_ROUTE_CODES:
        return _no_route(data.code)
    if data.code != "Ok":
        return _failed(data.code)
    if not data.routes:
        return _no_route("NoRoute")
    result: Coords = [(c[0], c[1]) for c in data.routes[0].geometry.coordinates]
    return _matched(result) if len(result) >= 2 else _failed("invalid_geometry")


def _matching_parts(points: TimedCoords) -> list[_RoutePart]:
    parts: list[_RoutePart] = []
    start = 0
    while start < len(points) - 1:
        end = min(start + MATCH_CHUNK_COORDS, len(points))
        parts.append(_RoutePart("matching", points[start:end]))
        if end == len(points):
            break
        start = end - 1
    return parts


def _plan_route(
    points: TimedCoords, profile: Profile
) -> tuple[list[_RoutePart], str | None]:
    if profile not in _DIRECTIONS_MAX_DISTANCE_KM:
        return [], "unsupported_profile"
    if any(b[2] <= a[2] for a, b in pairwise(points)):
        return [], "invalid_timestamps"
    if any(b[2] - a[2] >= MAX_TRACE_GAP_S for a, b in pairwise(points)):
        return [], "discontinuous_trace"

    if len(points) == 2:
        if total_length_km(_coords(points)) > _DIRECTIONS_MAX_DISTANCE_KM[profile]:
            return [], "directions_distance_limit"
        return [_RoutePart("directions", points)], None
    return _matching_parts(points), None


def route_request_batch_indices(
    pairs: list[tuple[TimedCoords, Profile]],
    max_requests: int = MAX_ROUTE_REQUESTS_PER_RUN,
) -> list[int]:
    """Return pair indices whose planned requests fit within one batch."""
    budget = _RequestBudget(max_requests)
    selected: list[int] = []
    for index, (points, profile) in enumerate(pairs):
        plan, planning_error = _plan_route(points, profile)
        requests = len(plan) if planning_error is None else 0
        if budget.reserve(requests):
            selected.append(index)
    return selected


async def _execute_route_plan(
    clients: MapboxRouteClients,
    plan: list[_RoutePart],
    profile: Profile,
    token: str,
    stats: RouteMatchStats | None,
) -> RouteMatchResult:
    results = await asyncio.gather(
        *(
            _fetch_matching(clients.matching, part.points, profile, token, stats)
            if part.operation == "matching"
            else _fetch_directions(
                clients.directions, part.points, profile, token, stats
            )
            for part in plan
        )
    )
    if failed := next(
        (result for result in results if result.status == RouteEnrichmentStatus.failed),
        None,
    ):
        return failed
    if no_route := next(
        (
            result
            for result in results
            if result.status == RouteEnrichmentStatus.no_route
        ),
        None,
    ):
        return no_route

    all_coords: Coords = []
    for result in results:
        if not result.route:
            return _failed("invalid_geometry")
        all_coords.extend(result.route[1:] if all_coords else result.route)
    return _matched(all_coords) if len(all_coords) >= 2 else _failed("invalid_geometry")


async def _match_one(  # noqa: PLR0913
    clients: MapboxRouteClients,
    points: TimedCoords,
    profile: Profile,
    token: str,
    stats: RouteMatchStats | None = None,
    budget: _RequestBudget | None = None,
) -> RouteMatchResult:
    """Match a single segment's GPS points to roads via Mapbox APIs."""
    if len(points) < 2:
        return _failed("insufficient_points")

    plan, planning_error = _plan_route(points, profile)
    if planning_error is not None:
        status = (
            _failed
            if planning_error in {"invalid_timestamps", "unsupported_profile"}
            else _no_route
        )
        return status(planning_error)
    if budget is not None and not budget.reserve(len(plan)):
        if stats is not None:
            stats.budget_fallbacks += 1
        return _no_route(REQUEST_BUDGET_EXCEEDED)

    result = await _execute_route_plan(clients, plan, profile, token, stats)

    if result.status != RouteEnrichmentStatus.matched or not result.route:
        logger.debug(
            "mapbox.segment_match_failed",
            profile=profile,
            point_count=len(points),
            status=result.status,
            error_code=result.error_code,
        )
        return result

    coords = _coords(points)
    span = total_length_km(coords)
    simplified = simplify_route(result.route, span)
    logger.debug(
        "mapbox.segment_matched",
        profile=profile,
        point_count=len(points),
        matched_point_count=len(result.route),
        simplified_point_count=len(simplified),
        length_km=span,
    )
    return _matched(simplified)


async def match_segments_with_stats(
    matching_client: MapboxClient,
    directions_client: MapboxClient,
    pairs: list[tuple[TimedCoords, Profile]],
) -> tuple[list[RouteMatchResult], RouteMatchStats]:
    """Match multiple segments, returning route results and HTTP request counts."""
    stats = RouteMatchStats()
    if not pairs:
        return [], stats

    token = _token()
    if not token:
        return [_failed("token_missing") for _ in pairs], stats

    clients = MapboxRouteClients(matching=matching_client, directions=directions_client)
    budget = _RequestBudget(MAX_ROUTE_REQUESTS_PER_RUN)
    with collect_http_transport_metrics() as transport_metrics:
        results = await asyncio.gather(
            *(
                _match_one(
                    clients,
                    points,
                    profile,
                    token,
                    stats,
                    budget,
                )
                for points, profile in pairs
            )
        )
    stats.outbound_attempts = transport_metrics.outbound_attempts
    stats.retries = max(
        0,
        stats.outbound_attempts - (stats.requests - stats.cache_hits),
    )
    stats.limiter_wait_ms = transport_metrics.limiter_wait_ms
    stats.provider_latency_ms = transport_metrics.provider_latency_ms
    return results, stats
