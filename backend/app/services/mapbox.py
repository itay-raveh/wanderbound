"""Mapbox Map Matching & Directions API client.

Density-based API selection: dense GPS → Map Matching, sparse → Directions.
Rate-limited to stay under Mapbox free-tier limits (60 req/min).
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


class _GeoJSONLineString(BaseModel):
    type: Literal["LineString"]
    coordinates: list[list[float]]


class _Matching(BaseModel):
    geometry: _GeoJSONLineString


class _MatchingResponse(BaseModel):
    matchings: list[_Matching] = []


class _Route(BaseModel):
    geometry: _GeoJSONLineString


class _DirectionsResponse(BaseModel):
    routes: list[_Route] = []


def _encode_coords(coords: Coords) -> str:
    return ";".join(f"{lon},{lat}" for lon, lat in coords)


def _token() -> str | None:
    token = get_settings().VITE_MAPBOX_TOKEN
    if not token:
        logger.warning("mapbox.token_missing")
    return token


async def _fetch_matching(
    client: httpx.AsyncClient,
    coords: Coords,
    profile: Profile,
    token: str,
    stats: RouteMatchStats | None = None,
) -> Coords | None:
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
            resp = await client.get(
                f"{_MATCHING_URL}/{profile}/{_encode_coords(reduced)}",
                params={
                    "geometries": "geojson",
                    "overview": "full",
                    "tidy": "true",
                    "access_token": token,
                },
            )
            set_span_data(span, **{"http.status_code": resp.status_code})
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "mapbox.matching_api_error",
                status_code=e.response.status_code,
            )
            return None
    data = _MatchingResponse.model_validate_json(resp.content)
    if not data.matchings:
        return None
    all_coords: Coords = []
    for matching in data.matchings:
        pts: Coords = [(c[0], c[1]) for c in matching.geometry.coordinates]
        all_coords.extend(pts[1:] if all_coords else pts)
    return all_coords if len(all_coords) >= 2 else None


async def _fetch_directions(
    client: httpx.AsyncClient,
    coords: Coords,
    profile: Profile,
    token: str,
    stats: RouteMatchStats | None = None,
) -> Coords | None:
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
            resp = await client.get(
                f"{_DIRECTIONS_URL}/{profile}/{_encode_coords(coords)}",
                params={
                    "geometries": "geojson",
                    "overview": "full",
                    "access_token": token,
                },
            )
            set_span_data(span, **{"http.status_code": resp.status_code})
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "mapbox.directions_api_error",
                status_code=e.response.status_code,
            )
            return None
    data = _DirectionsResponse.model_validate_json(resp.content)
    if not data.routes:
        return None
    result: Coords = [(c[0], c[1]) for c in data.routes[0].geometry.coordinates]
    return result if len(result) >= 2 else None


async def _chunked_route(
    coords: Coords,
    chunk_size: int,
    overlap: int,
    route_fn: Callable[[Coords], Coroutine[None, None, Coords | None]],
) -> Coords | None:
    chunks: list[Coords] = []
    start = 0
    while start < len(coords):
        end = min(start + chunk_size, len(coords))
        chunks.append(coords[start:end])
        if end == len(coords):
            break
        start += chunk_size - overlap

    results = await asyncio.gather(*[route_fn(c) for c in chunks])

    all_coords: Coords = []
    for piece in results:
        if piece is None:
            continue
        all_coords.extend(piece[1:] if all_coords else piece)
    return all_coords if len(all_coords) >= 2 else None


async def _match_one(
    clients: MapboxRouteClients,
    points_lonlat: Coords,
    profile: Profile,
    token: str,
    stats: RouteMatchStats | None = None,
) -> Coords | None:
    """Match a single segment's GPS points to roads via Mapbox APIs."""
    if len(points_lonlat) < 2:
        return None

    if is_sparse(points_lonlat):
        if len(points_lonlat) <= 25:
            raw = await _fetch_directions(
                clients.directions, points_lonlat, profile, token, stats
            )
        else:
            raw = await _chunked_route(
                points_lonlat,
                20,
                1,
                lambda c: _fetch_directions(
                    clients.directions, c, profile, token, stats
                ),
            )
    elif len(points_lonlat) <= MATCH_MAX_COORDS:
        raw = await _fetch_matching(
            clients.matching, points_lonlat, profile, token, stats
        )
    else:
        raw = await _chunked_route(
            points_lonlat,
            90,
            10,
            lambda c: _fetch_matching(clients.matching, c, profile, token, stats),
        )

    if raw is None:
        logger.debug(
            "mapbox.segment_match_failed",
            profile=profile,
            point_count=len(points_lonlat),
        )
        return None

    span = total_length_km(points_lonlat)
    simplified = simplify_route(raw, span)
    logger.debug(
        "mapbox.segment_matched",
        profile=profile,
        point_count=len(points_lonlat),
        matched_point_count=len(raw),
        simplified_point_count=len(simplified),
        length_km=span,
    )
    return simplified


async def match_segment(
    client: MapboxClient,
    points_lonlat: Coords,
    profile: Profile,
) -> Coords | None:
    """Match a single segment's GPS points to roads via Mapbox APIs.

    Automatically selects Map Matching (dense) or Directions (sparse).
    Returns road-snapped coordinates in [lon, lat] order, or None on failure.
    """
    token = _token()
    if not token:
        return None

    return await _match_one(
        MapboxRouteClients(matching=client, directions=client),
        points_lonlat,
        profile,
        token,
    )


async def match_segments(
    client: MapboxClient,
    pairs: list[tuple[Coords, Profile]],
) -> list[Coords | None]:
    """Match multiple segments concurrently, sharing one HTTP connection pool."""
    routes, _stats = await match_segments_with_stats(client, client, pairs)
    return routes


async def match_segments_with_stats(
    matching_client: MapboxClient,
    directions_client: MapboxClient,
    pairs: list[tuple[Coords, Profile]],
) -> tuple[list[Coords | None], RouteMatchStats]:
    """Match multiple segments, returning route results and HTTP request counts."""
    stats = RouteMatchStats()
    if not pairs:
        return [], stats

    token = _token()
    if not token:
        return [None] * len(pairs), stats

    clients = MapboxRouteClients(matching=matching_client, directions=directions_client)
    routes = await asyncio.gather(
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
    return routes, stats
