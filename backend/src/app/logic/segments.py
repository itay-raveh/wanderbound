import math
from datetime import datetime
from enum import StrEnum
from itertools import pairwise
from typing import TYPE_CHECKING, Self

import numpy as np
from pydantic import BaseModel

from app.core.logging import config_logger
from app.models.polarsteps import PSPoint, PSPoint as Point

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

_SPEED_MEANS_WINDOW = 5
_WALKING_SPEED_KMH = 5
_HIKE_MIN_TIME_H = 5
_HIKE_MIN_BBOX_DIAGONAL_KM = 5
_HIKE_MIN_KM = 8
_HIKE_MAX_GAP_H = 2
_HIKE_MAX_GAP_KM = 3

logger = config_logger(__name__)


class SegmentKind(StrEnum):
    flight = "flight"
    hike = "hike"
    other = "other"


Lon = float
Lat = float
LatLon = tuple[Lat, Lon]


class Segment(BaseModel):
    kind: SegmentKind
    start: datetime
    end: datetime
    length_km: float
    latlons: list[LatLon]

    @classmethod
    def from_points(cls, kind: SegmentKind, points: list[Point]) -> Self:
        return cls(
            kind=kind,
            start=points[0].datetime,
            end=points[-1].datetime,
            length_km=sum_distance_km(points),
            latlons=[(p.lat, p.lon) for p in sorted(points)],
        )


def _disk_km(p1_lon: float, p1_lat: float, p2_lon: float, p2_lat: float) -> float:
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(math.radians, [p1_lon, p1_lat, p2_lon, p2_lat])

    # haversine formula
    d_lon = lon2 - lon1
    d_lat = lat2 - lat1
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return c * 6371  # Radius of earth


def _dist_km_points(p1: Point, p2: Point) -> float:
    return _disk_km(*[p1.lon, p1.lat, p2.lon, p2.lat])


def sum_distance_km(points: Iterable[Point]) -> float:
    return sum(_dist_km_points(p1, p2) for p1, p2 in pairwise(points))


def _dist_time_speed(prev: Point, curr: Point) -> tuple[float, float, float]:
    dist_km = _dist_km_points(prev, curr)
    time_h = (curr.time - prev.time) / 3600.0
    return dist_km, time_h, dist_km / time_h


def clean_points(
    points: Iterable[Point],
    max_speed_kmh: float = 1000.0,
    spike_dist_threshold_km: float = 0.5,
    median_window: int = 3,
    max_smoothing_speed_kmh: int = 15,
) -> Iterable[Point]:
    # --- Phase 1: Sort & Deduplicate ---
    sorted_pts = sorted(points)
    unique_pts = [sorted_pts[0]]
    for p in sorted_pts[1:]:
        if p.time != unique_pts[-1].time:
            unique_pts.append(p)

    # --- Phase 2: Global Velocity Filter ---
    speed_filtered = _speed_filter(unique_pts, max_speed_kmh)
    speed_filtered = _speed_filter(speed_filtered, max_speed_kmh)

    if len(speed_filtered) < 3:
        yield from speed_filtered
        return

    # --- Phase 3: Spike / Zig-Zag Detection ---
    # Look at points A, B, and C. If B shoots far off, but C is close to A, B is noise.
    spike_filtered = _spike_filter(speed_filtered, spike_dist_threshold_km)
    spike_filtered = _spike_filter(spike_filtered, spike_dist_threshold_km)

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
            _, _, speed_kmh = _dist_time_speed(spike_filtered[i - 1], p)

        # Determine the final coordinates based on speed
        if speed_kmh < max_smoothing_speed_kmh:
            final_lat = smoothed_lats[i]
            final_lon = smoothed_lons[i]
        else:
            final_lat = p.lat
            final_lon = p.lon

        # Create the Pydantic Point with all required values at once
        yield Point(time=p.time, lat=final_lat, lon=final_lon)


def _max_speed(points: list[PSPoint]) -> float:
    max_speed_kmh = 0
    for prev, curr in pairwise(points):
        _, _, speed_kmh = _dist_time_speed(prev, curr)
        max_speed_kmh = max(max_speed_kmh, speed_kmh)
    return max_speed_kmh


def _speed_filter(
    points: list[PSPoint],
    max_speed_kmh: float,
) -> list[PSPoint]:
    speed_filtered = [points[0]]
    for i in range(1, len(points)):
        prev = speed_filtered[-1]
        curr = points[i]

        _, _, speed_kmh = _dist_time_speed(prev, curr)

        if speed_kmh <= max_speed_kmh:
            speed_filtered.append(curr)
    return speed_filtered


def _spike_filter(points: list[PSPoint], spike_dist_threshold_km: float) -> list[PSPoint]:
    spike_filtered = [points[0]]

    i = 1
    while i < len(points) - 1:
        a = spike_filtered[-1]
        b = points[i]
        c = points[i + 1]

        dist_ab = _dist_km_points(a, b)
        dist_ac = _dist_km_points(a, c)

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


def _extract_flights(
    points: list[Point],
    min_flight_speed_kmh: float = 200.0,
    min_flight_distance_km: float = 100.0,
) -> Generator[tuple[bool, list[Point]]]:
    if len(points) < 2:
        yield False, points
        return

    current_chunk = [points[0]]
    is_currently_flight = None

    for prev, curr in pairwise(points):
        _, _, speed_kmh = _dist_time_speed(prev, curr)
        current_speed_is_flight = speed_kmh >= min_flight_speed_kmh

        # Initialize the state on the very first edge
        if is_currently_flight is None:
            is_currently_flight = current_speed_is_flight

        # If the state remains the same, keep building the chunk
        if current_speed_is_flight == is_currently_flight:
            current_chunk.append(curr)

        # If the state changes (Drive -> Flight, or Flight -> Drive)
        else:
            # 1. Sanity Check: If concluding a flight, was it long enough?
            actual_is_flight = is_currently_flight
            if is_currently_flight:
                total_dist = _dist_km_points(current_chunk[0], current_chunk[-1])
                if total_dist < min_flight_distance_km:
                    actual_is_flight = False  # Failed the distance check, mark as noise/drive

            # 2. Yield the completed chunk
            yield actual_is_flight, current_chunk

            # 3. Start the new chunk.
            current_chunk = [prev, curr]
            is_currently_flight = current_speed_is_flight

    # Yield whatever is left in the buffer at the end of the dataset
    if len(current_chunk) > 1:
        actual_is_flight = is_currently_flight
        if is_currently_flight:
            total_dist = _dist_km_points(current_chunk[0], current_chunk[-1])
            if total_dist < min_flight_distance_km:
                actual_is_flight = False
        yield actual_is_flight, current_chunk  # pyright: ignore[reportReturnType]


def _group_points_by_walk(
    points: list[Point],
) -> Generator[tuple[bool, list[Point]]]:
    times = np.array([p.time for p in points])

    d_h = np.diff(times) / 3600.0
    d_km = np.array([_dist_km_points(p1, p2) for p1, p2 in pairwise(points)])

    with np.errstate(divide="ignore", invalid="ignore"):
        speeds = np.where(d_h > 0, d_km / d_h, 0.0)

    kernel = np.ones(_SPEED_MEANS_WINDOW) / _SPEED_MEANS_WINDOW
    smoothed_speeds = np.convolve(speeds, kernel, mode="same")

    is_walk = smoothed_speeds <= _WALKING_SPEED_KMH
    state_changes = np.diff(is_walk.astype(int))
    split_indices = np.where(state_changes != 0)[0] + 1  # pyright: ignore[reportAny]

    start_idx = 0
    current_is_walk: bool = is_walk[0]  # pyright: ignore[reportAny]

    for split_idx in split_indices:  # pyright: ignore[reportAny]
        yield current_is_walk, points[start_idx : split_idx + 1]
        start_idx = split_idx  # pyright: ignore[reportAny]
        current_is_walk = is_walk[split_idx]  # pyright: ignore[reportAssignmentType]

    yield current_is_walk, points[start_idx:]


def _merge_short_gaps(
    chunks: Iterable[tuple[bool, list[Point]]],
) -> list[tuple[bool, list[Point]]]:
    merged: list[tuple[bool, list[Point]]] = []

    for is_walk, chunk_points in chunks:
        if not merged:
            merged.append((is_walk, chunk_points))
            continue

        prev_is_walk, prev_points = merged[-1]

        # Check for a "Hike -> Other -> Hike" sandwich
        if is_walk and not prev_is_walk and len(merged) >= 2:
            prev_prev_is_walk = merged[-2][0]
            if prev_prev_is_walk:
                gap_duration = (prev_points[-1].time - prev_points[0].time) / 3600.0
                gap_distance = _dist_km_points(prev_points[-1], prev_points[0])

                if gap_duration < _HIKE_MAX_GAP_H and gap_distance < _HIKE_MAX_GAP_KM:
                    merged.pop()  # Remove the gap
                    _, first_hike_points = merged.pop()  # Remove the first hike

                    # Combine all three, ignoring duplicate boundary points
                    combined_points = first_hike_points + prev_points[1:] + chunk_points[1:]
                    merged.append((True, combined_points))
                    continue

        merged.append((is_walk, chunk_points))

    return merged


def _is_walk_chunk_a_hike(points: list[Point]) -> bool:
    if len(points) < 2:
        return False

    time_h = (points[-1].time - points[0].time) / 3600
    if time_h < _HIKE_MIN_TIME_H:
        return False

    dist_km = sum_distance_km(points)
    if dist_km < _HIKE_MIN_KM:
        return False

    # Extract all lons and lats into simple lists
    lons = [p.lon for p in points]
    lats = [p.lat for p in points]

    # Find the bounding box
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)

    # Calculate diagonal
    diagonal_km = _disk_km(min_lat, min_lon, max_lat, max_lon)

    return diagonal_km >= _HIKE_MIN_BBOX_DIAGONAL_KM


# noinspection PyTypeChecker
def _extract_hikes(points: list[Point]) -> Iterable[Segment]:
    if len(points) < 2:
        yield Segment.from_points(SegmentKind.other, points)
        return

    chunks = _merge_short_gaps(_group_points_by_walk(points))

    # Filter valid hikes and merge contiguous segments
    current_kind = None
    current_points = []

    for is_walk, chunk in chunks:
        chunk_kind = SegmentKind.other

        if is_walk and _is_walk_chunk_a_hike(chunk):
            chunk_kind = SegmentKind.hike

        # Yield and accumulate contiguous segments
        if current_kind is None:
            current_kind = chunk_kind
            current_points = chunk
        elif current_kind == chunk_kind:
            current_points.extend(chunk[1:])
        else:
            yield Segment.from_points(current_kind, current_points)
            current_kind = chunk_kind
            current_points = chunk

    if current_points:
        yield Segment.from_points(current_kind, current_points)  # pyright: ignore[reportArgumentType]


def build_segments(points: Iterable[Point]) -> Iterable[Segment]:
    clean = list(clean_points(points))
    for is_flight, chunk in _extract_flights(clean):
        if is_flight:
            yield Segment.from_points(kind=SegmentKind.flight, points=chunk)
        else:
            yield from _extract_hikes(chunk)
