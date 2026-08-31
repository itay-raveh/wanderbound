"""Mapbox Map Matching & Directions API client.

Density-based API selection: dense GPS → Map Matching, sparse → Directions.
Rate limiting is provided by the shared Mapbox HTTP clients.
"""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Literal

import httpx
import structlog
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.observability import set_span_data, start_span
from app.logic.route_matching import (
    Coords,
    is_sparse,
    reduce_coords,
    simplify_route,
    total_length_km,
)
from app.models.segment import RouteEnrichmentStatus

logger = structlog.get_logger(__name__)

type Profile = str  # "driving" or "walking"
type MapboxClient = httpx.AsyncClient

MATCH_MAX_COORDS = 100

_MATCHING_URL = "https://api.mapbox.com/matching/v5/mapbox"
_DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox"


@dataclass
class RouteMatchStats:
    matching_requests: int = 0
    directions_requests: int = 0

    @property
    def requests(self) -> int:
        return self.matching_requests + self.directions_requests


@dataclass(frozen=True)
class MapboxRouteClients:
    matching: MapboxClient
    directions: MapboxClient


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


def _token() -> str | None:
    token = get_settings().MAPBOX_TOKEN
    if not token:
        logger.warning("mapbox.token_missing")
    return token


async def _fetch_matching(
    client: httpx.AsyncClient,
    coords: Coords,
    profile: Profile,
    token: str,
    stats: RouteMatchStats | None = None,
) -> RouteMatchResult:
    if stats is not None:
        stats.matching_requests += 1
    reduced = reduce_coords(coords, MATCH_MAX_COORDS)
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
                    "access_token": token,
                },
            )
            set_span_data(span, **{"http.status_code": response.status_code})
        except httpx.RequestError as exc:
            logger.warning(
                "mapbox.matching_request_failed",
                error_type=type(exc).__name__,
            )
            raise MapboxTransientError("matching:request_failed") from exc
    if not response.is_success:
        return _http_failure(response, operation="matching")
    data = _MatchingResponse.model_validate_json(response.content)
    if data.code in _NO_ROUTE_CODES:
        return _no_route(data.code)
    if data.code != "Ok":
        return _failed(data.code)
    if not data.matchings:
        return _no_route("NoMatch")
    all_coords: Coords = []
    for matching in data.matchings:
        pts: Coords = [(c[0], c[1]) for c in matching.geometry.coordinates]
        all_coords.extend(pts[1:] if all_coords else pts)
    return _matched(all_coords) if len(all_coords) >= 2 else _failed("invalid_geometry")


async def _fetch_directions(
    client: httpx.AsyncClient,
    coords: Coords,
    profile: Profile,
    token: str,
    stats: RouteMatchStats | None = None,
) -> RouteMatchResult:
    if stats is not None:
        stats.directions_requests += 1
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


async def _chunked_route(
    coords: Coords,
    chunk_size: int,
    overlap: int,
    route_fn: Callable[[Coords], Coroutine[None, None, RouteMatchResult]],
) -> RouteMatchResult:
    chunks: list[Coords] = []
    start = 0
    while start < len(coords):
        end = min(start + chunk_size, len(coords))
        chunks.append(coords[start:end])
        if end == len(coords):
            break
        start += chunk_size - overlap

    results = await asyncio.gather(*[route_fn(c) for c in chunks])

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


async def _match_one(
    clients: MapboxRouteClients,
    points_lonlat: Coords,
    profile: Profile,
    token: str,
    stats: RouteMatchStats | None = None,
) -> RouteMatchResult:
    """Match a single segment's GPS points to roads via Mapbox APIs."""
    if len(points_lonlat) < 2:
        return _failed("insufficient_points")

    if is_sparse(points_lonlat):
        if len(points_lonlat) <= 25:
            result = await _fetch_directions(
                clients.directions, points_lonlat, profile, token, stats
            )
        else:
            result = await _chunked_route(
                points_lonlat,
                20,
                1,
                lambda c: _fetch_directions(
                    clients.directions, c, profile, token, stats
                ),
            )
    elif len(points_lonlat) <= MATCH_MAX_COORDS:
        result = await _fetch_matching(
            clients.matching, points_lonlat, profile, token, stats
        )
    else:
        result = await _chunked_route(
            points_lonlat,
            90,
            10,
            lambda c: _fetch_matching(clients.matching, c, profile, token, stats),
        )

    if result.status != RouteEnrichmentStatus.matched or not result.route:
        logger.debug(
            "mapbox.segment_match_failed",
            profile=profile,
            point_count=len(points_lonlat),
            status=result.status,
            error_code=result.error_code,
        )
        return result

    span = total_length_km(points_lonlat)
    simplified = simplify_route(result.route, span)
    logger.debug(
        "mapbox.segment_matched",
        profile=profile,
        point_count=len(points_lonlat),
        matched_point_count=len(result.route),
        simplified_point_count=len(simplified),
        length_km=span,
    )
    return _matched(simplified)


async def match_segment(
    client: MapboxClient,
    points_lonlat: Coords,
    profile: Profile,
) -> Coords | None:
    """Match a single segment's GPS points to roads via Mapbox APIs.

    Automatically selects Map Matching (dense) or Directions (sparse).
    Returns road-snapped coordinates in [lon, lat] order, or None when Mapbox
    reports no route or a permanent failure. Transient failures are raised.
    """
    token = _token()
    if not token:
        return None

    result = await _match_one(
        MapboxRouteClients(matching=client, directions=client),
        points_lonlat,
        profile,
        token,
    )
    return result.route


async def match_segments(
    client: MapboxClient,
    pairs: list[tuple[Coords, Profile]],
) -> list[Coords | None]:
    """Match multiple segments concurrently, sharing one HTTP connection pool."""
    results, _stats = await match_segments_with_stats(client, client, pairs)
    return [result.route for result in results]


async def match_segments_with_stats(
    matching_client: MapboxClient,
    directions_client: MapboxClient,
    pairs: list[tuple[Coords, Profile]],
) -> tuple[list[RouteMatchResult], RouteMatchStats]:
    """Match multiple segments, returning route results and HTTP request counts."""
    stats = RouteMatchStats()
    if not pairs:
        return [], stats

    token = _token()
    if not token:
        return [_failed("token_missing") for _ in pairs], stats

    clients = MapboxRouteClients(matching=matching_client, directions=directions_client)
    results = await asyncio.gather(
        *(
            _match_one(
                clients,
                coords,
                profile,
                token,
                stats,
            )
            for coords, profile in pairs
        )
    )
    return results, stats
