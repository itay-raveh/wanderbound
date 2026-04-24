import numpy as np
from simplification.cutil import simplify_coords_idx

from app.logic.spatial.geo import Coords, total_length_km
from app.models.segment import SegmentKind

MATCHABLE_KINDS = frozenset({SegmentKind.driving, SegmentKind.walking})

SPARSE_THRESHOLD_KM = 2

# RDP tolerances (degrees, approximate)
_RDP_TOLERANCES = [
    (10, 0.00001),  # < 10km: ~1m
    (100, 0.0001),  # < 100km: ~10m
    (float("inf"), 0.001),  # >= 100km: ~110m
]


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
