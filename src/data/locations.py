from itertools import pairwise
from pathlib import Path

from geopy.distance import distance
from pydantic import BaseModel

from src.core.logger import create_progress, get_logger

logger = get_logger(__name__)


class PathPoint(BaseModel):
    lat: float
    lon: float
    time: float


class LocationsJSON(BaseModel):
    locations: list[PathPoint]


class PathSegment(BaseModel):
    points: list[PathPoint]
    is_flight: bool


def _dist_and_speed(prev: PathPoint, curr: PathPoint) -> tuple[float, float]:
    dist_km = distance((prev.lat, prev.lon), (curr.lat, curr.lon)).km
    speed_kmh = dist_km / ((curr.time - prev.time) / 3600.0)
    return dist_km, speed_kmh


def load_locations(
    trip_dir: Path,
    min_time: float,
    max_time: float,
) -> tuple[list[PathPoint], list[PathSegment]]:
    locations_path = trip_dir / "locations.json"

    path_points = LocationsJSON.model_validate_json(locations_path.read_text()).locations
    path_points = [p for p in path_points if min_time <= p.time <= max_time]
    path_points.sort(key=lambda p: p.time)

    clean_points: list[PathPoint] = [path_points[0]]  # Hopefully the first point is not a GPS error

    with create_progress() as progress:
        for curr in progress.track(
            path_points[1:], description=f"Cleaning   {len(path_points):,} points..."
        ):
            prev = clean_points[-1]

            if prev.time == curr.time:
                continue

            _, speed_kmh = _dist_and_speed(prev, curr)

            if speed_kmh < 1500:
                clean_points.append(curr)

        segments: list[PathSegment] = []
        segment_points: list[PathPoint] = [path_points[0]]

        for prev, curr in progress.track(
            pairwise(clean_points),
            len(clean_points) - 1,
            description=f"Segmenting {len(clean_points):,} points...",
        ):
            dist_km, speed_kmh = _dist_and_speed(prev, curr)

            # Very fast over a large distance, must be a flight
            if speed_kmh > 150 and dist_km > 50:
                segments.append(PathSegment(points=segment_points, is_flight=False))
                segment_points = []
                segments.append(PathSegment(points=[prev, curr], is_flight=True))

            segment_points.append(curr)

        segments.append(PathSegment(points=segment_points, is_flight=False))

    logger.info("Loaded %d map points as %d segments", len(clean_points), len(segments))
    return clean_points, segments
