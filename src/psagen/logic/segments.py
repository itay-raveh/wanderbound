from __future__ import annotations

import itertools
from itertools import pairwise
from typing import TYPE_CHECKING

from geopy.distance import distance
from pydantic import BaseModel

from psagen.core.cache import async_cache
from psagen.core.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from psagen.models.trip import Step


logger = get_logger(__name__)


class PathPoint(BaseModel):
    lat: float
    lon: float
    time: float

    def __lt__(self, other: PathPoint) -> bool:
        return self.time < other.time


class Locations(BaseModel):
    locations: list[PathPoint]


class Segment(BaseModel):
    points: list[PathPoint]
    is_flight: bool


def _dist_and_speed(prev: PathPoint, curr: PathPoint) -> tuple[float, float]:
    dist_km = distance((prev.lat, prev.lon), (curr.lat, curr.lon)).km
    time_h = (curr.time - prev.time) / 3600.0
    return dist_km, dist_km / time_h


@async_cache
async def load_segments(
    locations: Locations, steps: Sequence[Step], progres_callback: Callable[[str], None]
) -> list[Segment]:
    progres_callback("Loading GPS points...")

    step_points = (
        PathPoint(lat=step.location.lat, lon=step.location.lat, time=step.start_time)
        for step in steps
    )

    min_time: float = steps[0].start_time
    max_time: float = steps[-1].start_time + 60 * 60 * 24

    points = sorted(
        point
        for point in itertools.chain(locations.locations, step_points)
        if min_time <= point.time <= max_time
    )

    progres_callback(f"Cleaning {len(points)} points...")

    clean_points = [points[0]]  # Hopefully the first point is not a GPS error
    for curr in points[1:]:
        prev = clean_points[-1]

        if prev.time == curr.time:
            continue

        _, speed_kmh = _dist_and_speed(prev, curr)

        if speed_kmh < 1000:
            clean_points.append(curr)

    progres_callback(f"Segmenting {len(clean_points)} points...")

    segments: list[Segment] = []
    segment_points: list[PathPoint] = [points[0]]

    for prev, curr in pairwise(clean_points):
        dist_km, speed_kmh = _dist_and_speed(prev, curr)

        # Very fast over a large distance, must be a flight
        if speed_kmh > 150 and dist_km > 50:
            segments.append(Segment(points=segment_points, is_flight=False))
            segment_points = []
            segments.append(Segment(points=[prev, curr], is_flight=True))

        segment_points.append(curr)

    segments.append(Segment(points=segment_points, is_flight=False))

    msg = f"Loaded {len(segments)} travel segments"
    progres_callback(msg)
    logger.info(msg)
    return segments
