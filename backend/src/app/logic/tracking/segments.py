from enum import StrEnum
from itertools import pairwise
from typing import TYPE_CHECKING, Self

import numpy as np
from pydantic import AwareDatetime, BaseModel

from app.core.logging import config_logger
from app.logic.tracking.cleaning import filter_duplicates
from app.logic.tracking.distance import dist_time_speed, distance_km, distance_km_coords

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Sequence

    from app.models.polarsteps import PSPoint

_SPEED_MEANS_WINDOW = 5
_WALKING_SPEED_KMH = 5
_HIKE_MIN_TIME_H = 5
_HIKE_MIN_BBOX_DIAGONAL_KM = 5
_HIKE_MIN_KM = 8
_HIKE_MAX_GAP_H = 5
_HIKE_MAX_GAP_KM = 8

logger = config_logger(__name__)


class SegmentKind(StrEnum):
    flight = "flight"
    hike = "hike"
    other = "other"


Lon = float
Lat = float
type LatLon = tuple[Lat, Lon]


class Segment(BaseModel):
    kind: SegmentKind
    start: AwareDatetime
    end: AwareDatetime
    length_km: float
    latlons: list[LatLon]

    @classmethod
    def from_points(cls, kind: SegmentKind, points: Sequence[PSPoint]) -> Self:
        return cls(
            kind=kind,
            start=points[0].datetime,
            end=points[-1].datetime,
            length_km=_sum_distance_km(points),
            latlons=[(p.lat, p.lon) for p in sorted(points)],
        )


def _sum_distance_km(points: Iterable[PSPoint]) -> float:
    return sum(distance_km(*pair) for pair in pairwise(points))


def _extract_flights(
    points: list[PSPoint],
    min_flight_speed_kmh: float = 200.0,
    min_flight_distance_km: float = 100.0,
) -> Generator[tuple[bool, list[PSPoint]]]:
    if len(points) <= 1:
        yield False, points
        return

    current_chunk = [points[0]]
    is_currently_flight = None

    for i in range(1, len(points)):
        _, _, speed_kmh = dist_time_speed(points[i - 1], points[i])
        is_edge_flight = speed_kmh >= min_flight_speed_kmh

        if is_currently_flight is None:
            is_currently_flight = is_edge_flight

        if is_edge_flight != is_currently_flight:
            is_valid = (
                is_currently_flight
                and distance_km(current_chunk[0], current_chunk[-1]) >= min_flight_distance_km
            )
            yield is_valid, current_chunk
            current_chunk = [points[i - 1]]
            is_currently_flight = is_edge_flight

        current_chunk.append(points[i])

    is_valid = bool(
        is_currently_flight
        and distance_km(current_chunk[0], current_chunk[-1]) >= min_flight_distance_km
    )

    yield is_valid, current_chunk


def _group_points_by_walk(
    points: list[PSPoint],
) -> Generator[tuple[bool, list[PSPoint]]]:
    times = np.array([p.time for p in points])

    d_h = np.diff(times) / 3600.0
    d_km = np.array([distance_km(p1, p2) for p1, p2 in pairwise(points)])

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
    chunks: Iterable[tuple[bool, list[PSPoint]]],
) -> list[tuple[bool, list[PSPoint]]]:
    merged: list[tuple[bool, list[PSPoint]]] = []

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
                gap_distance = distance_km(prev_points[-1], prev_points[0])

                if gap_duration < _HIKE_MAX_GAP_H and gap_distance < _HIKE_MAX_GAP_KM:
                    merged.pop()  # Remove the gap
                    _, first_hike_points = merged.pop()  # Remove the first hike

                    # Combine all three, ignoring duplicate boundary points
                    combined_points = first_hike_points + prev_points[1:] + chunk_points[1:]
                    merged.append((True, combined_points))
                    continue

        merged.append((is_walk, chunk_points))

    return merged


def _is_walk_chunk_a_hike(points: list[PSPoint]) -> bool:
    if len(points) < 2:
        return False

    time_h = (points[-1].time - points[0].time) / 3600
    if time_h < _HIKE_MIN_TIME_H:
        return False

    dist_km = _sum_distance_km(points)
    if dist_km < _HIKE_MIN_KM:
        return False

    # Extract all lons and lats into simple lists
    lons = [p.lon for p in points]
    lats = [p.lat for p in points]

    # Find the bounding box
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)

    # Calculate diagonal
    diagonal_km = distance_km_coords(min_lat, min_lon, max_lat, max_lon)

    return diagonal_km >= _HIKE_MIN_BBOX_DIAGONAL_KM


# noinspection PyTypeChecker
def _extract_hikes(points: list[PSPoint]) -> Iterable[Segment]:
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


def build_segments(points: Iterable[PSPoint]) -> Iterable[Segment]:
    unique = filter_duplicates(points)
    for is_flight, chunk in _extract_flights(unique):
        if is_flight:
            yield Segment.from_points(kind=SegmentKind.flight, points=chunk)
        else:
            yield from _extract_hikes(chunk)
