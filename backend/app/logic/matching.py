"""Mapbox map matching + RDP simplification for road-snapping GPS traces.

Ported from frontend/src/components/album/map/mapRouting.ts.
Density-based API selection: dense (<2km avg spacing) → Map Matching,
sparse (≥2km) → Directions. Results cached in DB via Segment.route.
"""

import asyncio
import logging
from math import atan2, cos, radians, sin, sqrt

import httpx

from app.core.config import get_settings
from app.models.segment import SegmentKind

logger = logging.getLogger(__name__)

type Coords = list[tuple[float, float]]  # [lon, lat] GeoJSON order
type Profile = str  # "driving" or "walking"

SPARSE_THRESHOLD_KM = 2
MATCH_MAX_COORDS = 100

MATCHABLE_KINDS = frozenset({SegmentKind.driving, SegmentKind.walking})

# RDP tolerances (degrees, approximate)
_RDP_TOLERANCES = [
    (10, 0.00005),  # < 10km: ~5m
    (100, 0.0002),  # < 100km: ~20m
    (float("inf"), 0.0005),  # >= 100km: ~50m
]


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))


def _total_length_km(coords: Coords) -> float:
    return sum(
        _haversine_km(*coords[i], *coords[i + 1]) for i in range(len(coords) - 1)
    )


def is_sparse(coords: Coords) -> bool:
    if len(coords) < 2:
        return False
    total = _total_length_km(coords)
    return total / (len(coords) - 1) > SPARSE_THRESHOLD_KM


def reduce_coords(coords: Coords, max_count: int) -> Coords:
    """Simplify coords to at most max_count points using RDP."""
    if len(coords) <= max_count:
        return coords
    tolerance = 0.0001
    result = coords
    while len(result) > max_count:
        result = _rdp(coords, tolerance)
        tolerance *= 2
    return result


def simplify_route(coords: Coords, span_km: float) -> Coords:
    """Apply RDP simplification based on segment span."""
    if len(coords) < 3:
        return coords
    for threshold, tol in _RDP_TOLERANCES:
        if span_km < threshold:
            return _rdp(coords, tol)
    return coords


def _rdp(coords: Coords, epsilon: float) -> Coords:
    """Ramer-Douglas-Peucker line simplification."""
    if len(coords) < 3:
        return coords

    start, end = coords[0], coords[-1]
    max_dist = 0.0
    max_idx = 0
    for i in range(1, len(coords) - 1):
        d = _perp_distance(coords[i], start, end)
        if d > max_dist:
            max_dist = d
            max_idx = i

    if max_dist > epsilon:
        left = _rdp(coords[: max_idx + 1], epsilon)
        right = _rdp(coords[max_idx:], epsilon)
        return left[:-1] + right
    return [start, end]


def _perp_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Perpendicular distance from point to line segment (in degrees)."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if dx == 0 and dy == 0:
        return sqrt((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2)
    t = max(
        0,
        min(
            1,
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
            / (dx * dx + dy * dy),
        ),
    )
    proj_x = start[0] + t * dx
    proj_y = start[1] + t * dy
    return sqrt((point[0] - proj_x) ** 2 + (point[1] - proj_y) ** 2)


def _encode_coords(coords: Coords) -> str:
    return ";".join(f"{lon},{lat}" for lon, lat in coords)


async def _fetch_matching(
    client: httpx.AsyncClient,
    coords: Coords,
    profile: Profile,
    token: str,
) -> Coords | None:
    reduced = reduce_coords(coords, MATCH_MAX_COORDS)
    url = (
        f"https://api.mapbox.com/matching/v5/mapbox/{profile}/"
        f"{_encode_coords(reduced)}"
        f"?geometries=geojson&overview=full&tidy=true&access_token={token}"
    )
    resp = await client.get(url)
    if resp.status_code != 200:
        logger.warning("Matching API error: %s", resp.status_code)
        return None
    data = resp.json()
    matchings = data.get("matchings", [])
    if not matchings:
        return None
    all_coords: Coords = []
    for matching in matchings:
        geom = matching.get("geometry", {})
        if geom.get("type") == "LineString":
            pts: Coords = [tuple(c) for c in geom["coordinates"]]
            all_coords.extend(pts[1:] if all_coords else pts)
    return all_coords if len(all_coords) >= 2 else None


async def _fetch_directions(
    client: httpx.AsyncClient,
    coords: Coords,
    profile: Profile,
    token: str,
) -> Coords | None:
    url = (
        f"https://api.mapbox.com/directions/v5/mapbox/{profile}/"
        f"{_encode_coords(coords)}"
        f"?geometries=geojson&overview=full&access_token={token}"
    )
    resp = await client.get(url)
    if resp.status_code != 200:
        logger.warning("Directions API error: %s", resp.status_code)
        return None
    data = resp.json()
    routes = data.get("routes", [])
    if not routes:
        return None
    geom_coords = routes[0].get("geometry", {}).get("coordinates", [])
    result: Coords = [tuple(c) for c in geom_coords]
    return result if len(result) >= 2 else None


async def _chunked_route(
    coords: Coords,
    chunk_size: int,
    overlap: int,
    route_fn: object,
) -> Coords | None:
    chunks: list[Coords] = []
    start = 0
    while start < len(coords):
        end = min(start + chunk_size, len(coords))
        chunks.append(coords[start:end])
        if end == len(coords):
            break
        start += chunk_size - overlap

    results = await asyncio.gather(*[route_fn(c) for c in chunks])  # type: ignore[operator]

    all_coords: Coords = []
    for piece in results:
        if piece is None:
            continue
        all_coords.extend(piece[1:] if all_coords else piece)
    return all_coords if len(all_coords) >= 2 else None


async def match_segment(
    points_lonlat: Coords,
    profile: Profile,
) -> Coords | None:
    """Match a segment's GPS points to roads via Mapbox APIs.

    Automatically selects Map Matching (dense) or Directions (sparse).
    Returns road-snapped coordinates in [lon, lat] order, or None on failure.
    """
    if len(points_lonlat) < 2:
        return None

    token = get_settings().MAPBOX_TOKEN
    if not token:
        logger.warning("No MAPBOX_TOKEN configured, skipping matching")
        return None

    async with httpx.AsyncClient(timeout=30) as client:
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
        return None

    span = _total_length_km(points_lonlat)
    return simplify_route(raw, span)
