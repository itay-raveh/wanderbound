"""Mapbox Map Matching & Directions API client.

Density-based API selection: dense GPS → Map Matching, sparse → Directions.
Rate-limited to stay under Mapbox free-tier limits (60 req/min).
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from functools import cache
from typing import Literal

import httpx
from aiolimiter import AsyncLimiter
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.http import RateLimitedTransport, cached_client
from app.logic.matching import (
    Coords,
    is_sparse,
    reduce_coords,
    simplify_route,
    total_length_km,
)

logger = logging.getLogger(__name__)

type Profile = str  # "driving" or "walking"

MATCH_MAX_COORDS = 100

_MATCHING_URL = "https://api.mapbox.com/matching/v5/mapbox"
_DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox"

# Mapbox free tier: 300 req/min (matching), 60 req/min (directions).
# Use the stricter limit as shared budget.
_limiter = AsyncLimiter(50, 60)


@cache
def _client() -> httpx.AsyncClient:
    return cached_client(transport=RateLimitedTransport(_limiter))


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
        logger.warning("No VITE_MAPBOX_TOKEN configured, skipping matching")
    return token


async def _fetch_matching(
    client: httpx.AsyncClient,
    coords: Coords,
    profile: Profile,
    token: str,
) -> Coords | None:
    reduced = reduce_coords(coords, MATCH_MAX_COORDS)
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
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.warning("Matching API error: %s", e.response.status_code)
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
) -> Coords | None:
    try:
        resp = await client.get(
            f"{_DIRECTIONS_URL}/{profile}/{_encode_coords(coords)}",
            params={
                "geometries": "geojson",
                "overview": "full",
                "access_token": token,
            },
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.warning("Directions API error: %s", e.response.status_code)
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
    client: httpx.AsyncClient,
    points_lonlat: Coords,
    profile: Profile,
    token: str,
) -> Coords | None:
    """Match a single segment's GPS points to roads via Mapbox APIs."""
    if len(points_lonlat) < 2:
        return None

    if is_sparse(points_lonlat):
        if len(points_lonlat) <= 25:
            raw = await _fetch_directions(client, points_lonlat, profile, token)
        else:
            raw = await _chunked_route(
                points_lonlat,
                20,
                1,
                lambda c: _fetch_directions(client, c, profile, token),
            )
    elif len(points_lonlat) <= MATCH_MAX_COORDS:
        raw = await _fetch_matching(client, points_lonlat, profile, token)
    else:
        raw = await _chunked_route(
            points_lonlat,
            90,
            10,
            lambda c: _fetch_matching(client, c, profile, token),
        )

    if raw is None:
        logger.debug(
            "Matching failed for %s segment (%d pts)",
            profile,
            len(points_lonlat),
        )
        return None

    span = total_length_km(points_lonlat)
    simplified = simplify_route(raw, span)
    logger.debug(
        "Matched %s segment: %d GPS → %d matched → %d simplified (%.1f km)",
        profile,
        len(points_lonlat),
        len(raw),
        len(simplified),
        span,
    )
    return simplified


async def match_segment(
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

    return await _match_one(_client(), points_lonlat, profile, token)


async def match_segments(
    pairs: list[tuple[Coords, Profile]],
) -> list[Coords | None]:
    """Match multiple segments concurrently, sharing one HTTP connection pool."""
    if not pairs:
        return []

    token = _token()
    if not token:
        return [None] * len(pairs)

    client = _client()
    return await asyncio.gather(
        *(_match_one(client, coords, profile, token) for coords, profile in pairs)
    )
