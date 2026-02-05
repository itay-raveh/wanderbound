from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING

from geopy.distance import distance
from pydantic import BaseModel
from shapely.geometry import LineString

from src.core.cache import async_cache
from src.core.logger import create_progress, get_logger

if TYPE_CHECKING:
    from pathlib import Path


logger = get_logger(__name__)


class PathPoint(BaseModel):
    lat: float
    lon: float
    time: float

    def __lt__(self, other: PathPoint) -> bool:
        return self.time < other.time


class LocationsJSON(BaseModel):
    locations: list[PathPoint]


class Segment(BaseModel):
    points: list[PathPoint]
    is_flight: bool


def simplify_segments(segments: list[Segment], tolerance: float = 0.005) -> list[Segment]:
    """Simplify segments using Ramer-Douglas-Peucker algorithm via shapely."""
    simplified: list[Segment] = []
    for segment in segments:
        if len(segment.points) < 3:
            simplified.append(segment)
            continue

        coords = [(p.lon, p.lat) for p in segment.points]
        line = LineString(coords)
        simplified_line = line.simplify(tolerance, preserve_topology=False)

        if simplified_line.is_empty:
            continue

        # Reconstruct PathPoints (losing time data, set to 0.0)
        new_points = [PathPoint(lat=y, lon=x, time=0.0) for x, y in simplified_line.coords]
        simplified.append(Segment(points=new_points, is_flight=segment.is_flight))

    return simplified


def _dist_and_speed(prev: PathPoint, curr: PathPoint) -> tuple[float, float]:
    dist_km = distance((prev.lat, prev.lon), (curr.lat, curr.lon)).km
    time_h = (curr.time - prev.time) / 3600.0
    return dist_km, dist_km / time_h


@async_cache
def load_segments(
    trip_dir: Path,
    step_points: list[tuple[float, float, float]],
    min_time: float,
    max_time: float,
) -> list[Segment]:
    locations_json = LocationsJSON.model_validate_json(
        (trip_dir / "locations.json").read_text(encoding="utf-8")
    )

    path_points = locations_json.locations + [
        PathPoint(lat=lat, lon=lon, time=time) for lat, lon, time in step_points
    ]

    with create_progress("Loading GPS points") as progress:
        tracked_points = progress.track(path_points, description="Filtering...")
        points = sorted(point for point in tracked_points if min_time <= point.time <= max_time)

        clean_points = [points[0]]  # Hopefully the first point is not a GPS error
        for curr in progress.track(points[1:], description="Cleaning..."):
            prev = clean_points[-1]

            if prev.time == curr.time:
                continue

            _, speed_kmh = _dist_and_speed(prev, curr)

            if speed_kmh < 1000:
                clean_points.append(curr)

        segments: list[Segment] = []
        segment_points: list[PathPoint] = [points[0]]

        for prev, curr in progress.track(
            pairwise(clean_points), len(clean_points) - 1, description="Segmenting..."
        ):
            dist_km, speed_kmh = _dist_and_speed(prev, curr)

            # Very fast over a large distance, must be a flight
            if speed_kmh > 150 and dist_km > 50:
                segments.append(Segment(points=segment_points, is_flight=False))
                segment_points = []
                segments.append(Segment(points=[prev, curr], is_flight=True))

            segment_points.append(curr)

        segments.append(Segment(points=segment_points, is_flight=False))

    return segments
