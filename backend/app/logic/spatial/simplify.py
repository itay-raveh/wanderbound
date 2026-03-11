# pyright: reportAny=false

from typing import TYPE_CHECKING, cast

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


# https://en.wikipedia.org/wiki/Ramer%E2%80%93Douglas%E2%80%93Peucker_algorithm
def rdp_mask(
    lats: NDArray[np.float64], lons: NDArray[np.float64], epsilon_deg: float
) -> NDArray[np.bool_]:
    """Ramer-Douglas-Peucker algorithm implementation.

    Returns a boolean mask of the points to keep.
    """
    n = len(lats)
    keep = np.ones(n, dtype=bool)
    if n <= 2:
        return keep

    pts = np.column_stack((lons, lats))
    stack = [(0, n - 1)]

    while stack:
        start, end = stack.pop()
        if end - start <= 1:
            continue

        line_start = pts[start]
        line_end = pts[end]

        line_vec = line_end - line_start
        line_len = np.hypot(line_vec[0], line_vec[1])

        window_pts = pts[start + 1 : end]

        if line_len == 0.0:
            # Start and end are exactly the same point
            dists = np.hypot(
                window_pts[:, 0] - line_start[0], window_pts[:, 1] - line_start[1]
            )
        else:
            # Perpendicular distance = |cross_product(line_vec, point_vec)| / line_len
            cross_prods = np.abs(
                line_vec[0] * (window_pts[:, 1] - line_start[1])
                - line_vec[1] * (window_pts[:, 0] - line_start[0])
            )
            dists = cross_prods / line_len

        max_idx = int(np.argmax(dists))
        max_dist = cast("float", dists[max_idx])

        if max_dist > epsilon_deg:
            # Split at max_idx (which is relative to start + 1)
            split_idx = start + 1 + max_idx
            stack.append((start, split_idx))
            stack.append((split_idx, end))
        else:
            # All points between start and end are within epsilon, discard them
            keep[start + 1 : end] = False

    return keep
