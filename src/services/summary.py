"""Trip summary calculation service."""

from datetime import datetime
from zoneinfo import ZoneInfo

from geopy.distance import geodesic

from src.core.logger import get_logger
from src.data.models import AlbumPhotoData, Step, StepData, TripSummary

logger = get_logger(__name__)


def calculate_trip_summary(
    steps: list[Step],
    step_data_list: list[StepData],
    photo_data: AlbumPhotoData,
) -> TripSummary:
    """Calculate summary statistics for the trip."""
    logger.info("Calculating trip summary for %d steps", len(steps))

    # Countries with flags
    countries: list[tuple[str, str | None]] = []
    seen_countries = set()

    # Photo count for filtered steps
    photo_count = 0

    # Use step_data_list for flags as it contains enriched data
    for step_data in step_data_list:
        country = step_data.country
        if country and country not in seen_countries:
            flag_url = step_data.country_flag_data_uri
            countries.append((country, flag_url))
            seen_countries.add(country)

    # Re-iterating to be clean or we can do it in one pass if we have access.
    # The `Step` object in `src/data/models.py` does NOT have elevation.
    # Elevation is in `fetched_data.elevations`.
    # `calculate_trip_summary` is called in `generator.py` AFTER `_process_steps`.
    # But `_process_steps` creates `StepData`.
    # `calculate_trip_summary` receives `steps: list[Step]`.
    # We might need to pass `step_data_list` instead of `steps` to get elevation?
    # Or just use `photo_data` for photos.

    # Let's fix photo count first
    for step in steps:
        if step.id in photo_data.steps_with_photos:
            photo_count += len(photo_data.steps_with_photos[step.id])

    # Total Distance (Geodesic)
    total_km = 0.0
    for i in range(len(steps) - 1):
        start = (steps[i].location.lat, steps[i].location.lon)
        end = (steps[i + 1].location.lat, steps[i + 1].location.lon)
        dist = geodesic(start, end).kilometers
        total_km += dist

    logger.info("Calculated total_km: %.2f for %d steps", total_km, len(steps))

    # Total Days & Dates
    start_date_str = None
    end_date_str = None
    if steps:
        start_time = steps[0].start_time
        end_time = steps[-1].start_time
        total_days = int((end_time - start_time) / (24 * 3600)) + 1

        # Format dates
        start_tz = ZoneInfo(steps[0].timezone_id)
        end_tz = ZoneInfo(steps[-1].timezone_id)

        start_date_str = datetime.fromtimestamp(start_time, tz=start_tz).strftime("%d %b %Y")
        end_date_str = datetime.fromtimestamp(end_time, tz=end_tz).strftime("%d %b %Y")
    else:
        total_days = 0

    return TripSummary(
        countries=countries,
        total_km=round(total_km),
        total_days=total_days,
        step_count=len(steps),
        photo_count=photo_count,
        start_date=start_date_str,
        end_date=end_date_str,
    )
