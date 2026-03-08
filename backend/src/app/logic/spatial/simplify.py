import numpy as np


def rdp_mask(lats: np.ndarray, lons: np.ndarray, epsilon_deg: float) -> np.ndarray:
    """
    Ramer-Douglas-Peucker algorithm implementation.
    Returns a boolean mask of the points to keep.
    """
    n = len(lats)
    keep = np.ones(n, dtype=bool)
    if n <= 2:
        return keep

    # Stack to avoid recursion limits and python call overhead
    # Stack stores tuples of (start_index, end_index)
    stack = [(0, n - 1)]

    # We do calculations in degrees.
    # For small areas, Euclidean distance on lat/lon is a sufficient approximation for visual simplification.
    pts = np.column_stack((lons, lats))

    while stack:
        start, end = stack.pop()
        if end - start <= 1:
            continue

        # Line from start to end
        line_start = pts[start]
        line_end = pts[end]

        # Line vector
        line_vec = line_end - line_start
        line_len = np.hypot(line_vec[0], line_vec[1])

        window_pts = pts[start + 1 : end]

        if line_len == 0.0:
            # Start and end are exactly the same point
            dists = np.hypot(window_pts[:, 0] - line_start[0], window_pts[:, 1] - line_start[1])
        else:
            # Perpendicular distance = |cross_product(line_vec, point_vec)| / line_len
            # point_vec = pt - line_start
            cross_prods = np.abs(
                line_vec[0] * (window_pts[:, 1] - line_start[1])
                - line_vec[1] * (window_pts[:, 0] - line_start[0])
            )
            dists = cross_prods / line_len

        max_idx = np.argmax(dists)
        max_dist = dists[max_idx]

        if max_dist > epsilon_deg:
            # Split at max_idx (which is relative to start + 1)
            split_idx = start + 1 + max_idx
            stack.append((start, split_idx))
            stack.append((split_idx, end))
        else:
            # All points between start and end are within epsilon, discard them
            keep[start + 1 : end] = False

    return keep
