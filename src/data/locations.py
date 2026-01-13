import math
from itertools import pairwise
from pathlib import Path

from geopy.distance import distance
from pydantic import BaseModel

from src.core.logger import get_logger

logger = get_logger(__name__)


class PathPoint(BaseModel):
    lat: float
    lon: float
    time: float


class LocationEntries(BaseModel):
    locations: list[PathPoint]


class PathSegment(BaseModel):
    points: list[PathPoint]
    is_flight: bool


def detect_segments(locations: list[PathPoint]) -> list[PathSegment]:
    """Split locations into ground and flight segments based on speed and distance."""
    segments: list[PathSegment] = []
    points: list[PathPoint] = [locations[0]]

    for prev, curr in pairwise(locations):
        dist_km = distance((prev.lat, prev.lon), (curr.lat, curr.lon)).km
        speed_kmh = dist_km / ((curr.time - prev.time) / 3600.0)

        # Very fast over a large distance, must be a flight
        if speed_kmh > 150 and dist_km > 50:
            segments.append(PathSegment(points=points, is_flight=False))
            points = []
            segments.append(PathSegment(points=[prev, curr], is_flight=True))

        points.append(curr)

    segments.append(PathSegment(points=points, is_flight=False))

    return segments


def _filter_outliers(locations: list[PathPoint], max_speed_kmh: float = 1500.0) -> list[PathPoint]:
    """Remove points that imply travel speeds greater than max_speed_kmh.

    This is calculated relative to the last valid point.

    Args:
        locations: List of Location objects sorted by time.
        max_speed_kmh: Maximum allowed speed in km/h. Default 1500 (supersonic).

    Returns:
        Filtered list of Location objects.
    """
    if not locations:
        return []

    valid_locations = [locations[0]]
    removed_count = 0

    # Iterate starting from the second point
    for current in locations[1:]:
        last_valid = valid_locations[-1]

        # Calculate time difference in hours
        time_diff_hours = (current.time - last_valid.time) / 3600.0

        if time_diff_hours <= 0:
            # Duplicate or out-of-order time; simpler to just drop or keep.
            # If strictly 0 time and distance > 0, it's impossible.
            # Let's drop if time is 0 to avoid division by zero
            removed_count += 1
            continue

        distance_km = distance((last_valid.lat, last_valid.lon), (current.lat, current.lon)).km

        speed = distance_km / time_diff_hours

        if speed > max_speed_kmh:
            # Outlier detected
            removed_count += 1
            continue

        valid_locations.append(current)

    if removed_count > 0:
        logger.info("Removed %d outlier points (speed > %s km/h)", removed_count, max_speed_kmh)

    return valid_locations


def load_locations(
    locations_path: Path,
    min_time: float | None = None,
    max_time: float | None = None,
) -> list[PathPoint]:
    """Load, parse, clean, and filter location data from a JSON file.

    Args:
        locations_path: Path to the locations.json file.
        min_time: Optional start timestamp to filter points.
        max_time: Optional end timestamp to filter points.

    Returns:
        List of LocationEntry objects. Raises on failure.
    """
    start_t = min_time if min_time is not None else -math.inf
    end_t = max_time if max_time is not None else math.inf

    points = LocationEntries.model_validate_json(
        locations_path.read_text(encoding="utf-8")
    ).locations
    points.sort(key=lambda x: x.time)
    points = [p for p in points if start_t <= p.time <= end_t]
    points = _filter_outliers(points)

    logger.info("Processed %d map points", len(points))
    return points
