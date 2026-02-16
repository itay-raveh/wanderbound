from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING

from geopy.distance import distance
from pydantic import BaseModel, field_validator
from shapely.geometry import LineString

from psagen.core.cache import async_cache
from psagen.core.logger import get_logger

if TYPE_CHECKING:
    from pathlib import Path


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

    @field_validator("points")
    @classmethod
    def simplify(cls, points: list[PathPoint]) -> list[PathPoint]:
        coords = [(p.lon, p.lat) for p in points]
        simplified = LineString(coords).simplify(5, preserve_topology=False)
        return [PathPoint(lat=y, lon=x, time=0.0) for x, y in simplified.coords]


def _dist_and_speed(prev: PathPoint, curr: PathPoint) -> tuple[float, float]:
    dist_km = distance((prev.lat, prev.lon), (curr.lat, curr.lon)).km
    time_h = (curr.time - prev.time) / 3600.0
    return dist_km, dist_km / time_h


@async_cache
def load_segments(
    locations_json_path: Path,
    step_points: list[tuple[float, float, float]],
    min_time: float,
    max_time: float,
) -> list[Segment]:
    locations_json = Locations.model_validate_json(locations_json_path.read_text(encoding="utf-8"))

    path_points = locations_json.locations + [
        PathPoint(lat=lat, lon=lon, time=time) for lat, lon, time in step_points
    ]

    points = sorted(point for point in path_points if min_time <= point.time <= max_time)

    clean_points = [points[0]]  # Hopefully the first point is not a GPS error
    for curr in points[1:]:
        prev = clean_points[-1]

        if prev.time == curr.time:
            continue

        _, speed_kmh = _dist_and_speed(prev, curr)

        if speed_kmh < 1000:
            clean_points.append(curr)

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

    logger.info("Loaded %d travel segments", len(segments))
    return segments
