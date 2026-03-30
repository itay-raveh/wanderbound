import numpy as np
from simplification.cutil import simplify_coords_idx

from app.logic.spatial.geo import haversine_km
from app.models.segment import SegmentKind

type Coords = list[tuple[float, float]]  # [lon, lat] GeoJSON order

MATCHABLE_KINDS = frozenset({SegmentKind.driving, SegmentKind.walking})

SPARSE_THRESHOLD_KM = 2

# RDP tolerances (degrees, approximate)
_RDP_TOLERANCES = [
    (10, 0.00005),  # < 10km: ~5m
    (100, 0.0002),  # < 100km: ~20m
    (float("inf"), 0.0005),  # >= 100km: ~50m
]


def total_length_km(coords: Coords) -> float:
    """Total length of a coordinate list in km. Coords are (lon, lat) GeoJSON order."""
    return sum(
        haversine_km(coords[i][1], coords[i][0], coords[i + 1][1], coords[i + 1][0])
        for i in range(len(coords) - 1)
    )


def is_sparse(coords: Coords) -> bool:
    if len(coords) < 2:
        return False
    total = total_length_km(coords)
    return total / (len(coords) - 1) > SPARSE_THRESHOLD_KM


def reduce_coords(coords: Coords, max_count: int) -> Coords:
    """Simplify coords to at most max_count points using RDP."""
    if len(coords) <= max_count:
        return coords
    tolerance = 0.0001
    result = coords
    while len(result) > max_count and tolerance < 1.0:
        result = _simplify(result, tolerance)
        tolerance *= 2
    return result


def simplify_route(coords: Coords, span_km: float) -> Coords:
    """Apply RDP simplification based on segment span."""
    if len(coords) < 3:
        return coords
    for threshold, tol in _RDP_TOLERANCES:
        if span_km < threshold:
            return _simplify(coords, tol)
    return coords


def _simplify(coords: Coords, epsilon: float) -> Coords:
    """RDP simplification via the simplification C library."""
    if len(coords) < 3:
        return coords
    indices = simplify_coords_idx(np.array(coords), epsilon)
    return [coords[i] for i in indices]
