import numpy as np
from simplification.cutil import simplify_coords_idx

from app.logic.spatial.geo import Coords
from app.models.segment import SegmentKind

MATCHABLE_KINDS = frozenset({SegmentKind.driving, SegmentKind.walking})

# RDP tolerances (degrees, approximate)
_RDP_TOLERANCES = [
    (10, 0.00001),  # < 10km: ~1m
    (100, 0.0001),  # < 100km: ~10m
    (float("inf"), 0.001),  # >= 100km: ~110m
]


def reduce_coord_indices(coords: Coords, max_count: int) -> list[int]:
    """Return RDP-selected indices so parallel metadata stays aligned."""
    if len(coords) <= max_count:
        return list(range(len(coords)))
    tolerance = 0.0001
    indices = list(range(len(coords)))
    result = coords
    while len(result) > max_count and tolerance < 1.0:
        selected = simplify_coords_idx(np.array(result), tolerance).tolist()
        indices = [indices[i] for i in selected]
        result = [result[i] for i in selected]
        tolerance *= 2
    if len(indices) > max_count:
        positions = np.linspace(0, len(indices) - 1, max_count, dtype=int)
        indices = [indices[i] for i in positions]
    return indices


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
