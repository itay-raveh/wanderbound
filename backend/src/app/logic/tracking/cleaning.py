from typing import TYPE_CHECKING

import numpy as np

from app.logic.tracking.distance import dist_time_speed, distance_km

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.models.polarsteps import PSPoint


def clean_points(
    points: Iterable[PSPoint],
    max_speed_kmh: float = 1000.0,
    spike_dist_threshold_km: float = 0.5,
    median_window: int = 3,
    max_smoothing_speed_kmh: int = 15,
) -> Iterable[PSPoint]:
    # --- Phase 1: Sort & Deduplicate ---
    unique_pts = filter_duplicates(points)

    if len(unique_pts) <= 2:
        yield from unique_pts
        return

    # --- Phase 2: Global Velocity Filter ---
    speed_filtered = _filter_speed(unique_pts, max_speed_kmh)

    if len(speed_filtered) < 3:
        yield from speed_filtered
        return

    # --- Phase 3: Spike / Zig-Zag Detection ---
    # Look at points A, B, and C. If B shoots far off, but C is close to A, B is noise.
    spike_filtered = _filter_spikes(speed_filtered, spike_dist_threshold_km)

    # --- Phase 4: Speed-Gated NumPy Rolling Median ---
    # Only smooth when moving slowly to preserve high-speed geometry
    if len(spike_filtered) < median_window:
        yield from spike_filtered
        return

    # Extract coordinates into arrays
    lats = np.array([p.lat for p in spike_filtered])
    lons = np.array([p.lon for p in spike_filtered])

    # Pad arrays to handle edges
    pad_size = median_window // 2
    padded_lats = np.pad(lats, (pad_size, pad_size), mode="edge")
    padded_lons = np.pad(lons, (pad_size, pad_size), mode="edge")

    # Calculate smoothed medians for ALL points in the background
    smoothed_lats: list[float] = [
        np.median(padded_lats[j : j + median_window]) for j in range(len(lats))
    ]
    smoothed_lons: list[float] = [
        np.median(padded_lons[j : j + median_window]) for j in range(len(lons))
    ]

    for i, p in enumerate(spike_filtered):
        # Determine local speed (default to 0 for the first point)
        if i == 0:
            speed_kmh = 0.0
        else:
            # Reusing your helper function to get the speed from the previous point
            _, _, speed_kmh = dist_time_speed(spike_filtered[i - 1], p)

        if speed_kmh < max_smoothing_speed_kmh:
            p.lat = smoothed_lats[i]
            p.lon = smoothed_lons[i]

        yield p


def filter_duplicates(points: Iterable[PSPoint]) -> list[PSPoint]:
    sorted_pts = sorted(points)
    if len(sorted_pts) < 2:
        return sorted_pts
    unique_pts = [sorted_pts[0]]
    for p in sorted_pts[1:]:
        if p.time != unique_pts[-1].time:
            unique_pts.append(p)
    return unique_pts


def _filter_speed(
    points: list[PSPoint],
    max_speed_kmh: float,
) -> list[PSPoint]:
    speed_filtered = [points[0]]
    for i in range(1, len(points)):
        prev = speed_filtered[-1]
        curr = points[i]

        _, _, speed_kmh = dist_time_speed(prev, curr)

        if speed_kmh <= max_speed_kmh:
            speed_filtered.append(curr)
    return speed_filtered


def _filter_spikes(points: list[PSPoint], spike_dist_threshold_km: float) -> list[PSPoint]:
    spike_filtered = [points[0]]

    i = 1
    while i < len(points) - 1:
        a = spike_filtered[-1]
        b = points[i]
        c = points[i + 1]

        dist_ab = distance_km(a, b)
        dist_ac = distance_km(a, c)

        # If B jumps far away, but C returns close to A...
        if dist_ab > spike_dist_threshold_km and dist_ac < (dist_ab * 0.5):
            # B is a spike anomaly. We skip it and move to the next point.
            i += 1
            continue

        spike_filtered.append(b)
        i += 1

    # Don't forget the last point
    if points[-1] not in spike_filtered:
        spike_filtered.append(points[-1])

    return spike_filtered
