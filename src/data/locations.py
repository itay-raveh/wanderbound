import math
from pathlib import Path

from geopy.distance import distance
from pydantic import (
    BaseModel,
    Field,
)

from src.core.logger import get_logger

logger = get_logger(__name__)


class Location(BaseModel):
    country: str = Field(alias="detail")
    country_code: str = Field(pattern=r"^[A-Za-z]{2}$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class LocationEntry(BaseModel):
    lat: float
    lon: float
    time: float


class LocationEntries(BaseModel):
    locations: list[LocationEntry]


class TravelSegment(BaseModel):
    points: list[LocationEntry]
    is_flight: bool


def detect_segments(
    locations: list[LocationEntry],
    min_flight_speed_kmh: float = 150.0,
    min_flight_dist_km: float = 50.0,
) -> list[TravelSegment]:
    """Split locations into ground and flight segments based on speed and distance."""
    if not locations:
        return []

    segments: list[TravelSegment] = []
    current_points: list[LocationEntry] = [locations[0]]

    for i in range(len(locations) - 1):
        p1 = locations[i]
        p2 = locations[i + 1]

        dist_km = distance((p1.lat, p1.lon), (p2.lat, p2.lon)).kilometers
        time_diff_hours = (p2.time - p1.time) / 3600.0

        if time_diff_hours <= 0:
            current_points.append(p2)
            continue

        speed_kmh = dist_km / time_diff_hours

        # Check for flight conditions
        is_flight = speed_kmh > min_flight_speed_kmh and dist_km > min_flight_dist_km

        if is_flight:
            # 1. Close current ground segment if it has points
            if current_points:
                # If the last point is p1, it's included here
                segments.append(TravelSegment(points=current_points, is_flight=False))

            # 2. Add the flight segment (p1 -> p2)
            segments.append(TravelSegment(points=[p1, p2], is_flight=True))

            # 3. Start new ground segment from p2
            current_points = [p2]
        else:
            current_points.append(p2)

    # processing the last segment
    if current_points:
        segments.append(TravelSegment(points=current_points, is_flight=False))

    return segments


def _filter_outliers(
    locations: list[LocationEntry], max_speed_kmh: float = 1500.0
) -> list[LocationEntry]:
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
) -> list[LocationEntry]:
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
