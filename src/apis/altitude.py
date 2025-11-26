"""Altitude/elevation API integration."""

import httpx
from more_itertools import chunked

from ..logger import create_progress, get_logger
from ..settings import get_settings
from .cache import get_cached, set_cached
from .rate_limit import fetch_json_with_retry

logger = get_logger(__name__)

# OpenTopoData API rate limit: 1000 requests/day = ~1 request per 86 seconds
# Using 1 request per second to allow for some burst while staying safe
API_CALLS_PER_SECOND = 1


def get_altitude_batch(locations: list[tuple[float, float]]) -> list[float | None]:
    """Get altitude for multiple coordinates using OpenTopoData API with batching."""
    all_elevations: list[float | None] = []
    locations_to_query: list[tuple[float, float]] = []

    for loc in locations:
        lat, lon = loc
        cache_key = f"elevation_{lat},{lon}"
        cached_value = get_cached(cache_key)
        if cached_value is not None and isinstance(cached_value, (int, float)):
            all_elevations.append(float(cached_value))
        else:
            locations_to_query.append(loc)

    max_locations_per_request = 100
    max_calls_per_day = 1000
    calls_made = 0

    # Calculate number of batches for progress bar
    num_batches = (
        len(locations_to_query) + max_locations_per_request - 1
    ) // max_locations_per_request
    progress = create_progress("Fetching elevations")

    with progress:
        task_id = progress.add_task("Fetching elevations", total=num_batches)
        for batch in chunked(locations_to_query, max_locations_per_request):
            if calls_made >= max_calls_per_day:
                logger.warning("Reached maximum API calls for today. Using cached data only.")
                all_elevations.extend([None] * len(batch))
                progress.advance(task_id)
                continue

            locations_param = "|".join([f"{lat},{lon}" for lat, lon in batch])
            url = get_settings().opentopodata_api_url.format(locations=locations_param)

            try:
                logger.debug(
                    "Fetching elevation for batch of %d locations (call %d)",
                    len(batch),
                    calls_made + 1,
                )
                progress.update(
                    task_id,
                    description=f"Fetching elevations: batch {calls_made + 1}/{num_batches}",
                )
                data = fetch_json_with_retry(url, calls_per_second=API_CALLS_PER_SECOND)

                if "results" in data:
                    for loc, result in zip(batch, data["results"], strict=True):
                        lat, lon = loc
                        elevation_raw = result.get("elevation")
                        elevation: float | None = (
                            float(elevation_raw)
                            if elevation_raw is not None and isinstance(elevation_raw, (int, float))
                            else None
                        )
                        all_elevations.append(elevation)

                        cache_key = f"elevation_{lat},{lon}"
                        set_cached(cache_key, elevation)
                    logger.debug(f"Cached {len(batch)} elevations")
                else:
                    logger.warning("No results in elevation API response for batch")
                    all_elevations.extend([None] * len(batch))

                calls_made += 1
                progress.advance(task_id)

            except httpx.RequestError as e:
                logger.warning(f"Failed to get elevation for batch: {e}")
                all_elevations.extend([None] * len(batch))
                progress.advance(task_id)
            except (KeyError, ValueError) as e:
                logger.error(f"Error parsing elevation response: {e}", exc_info=True)
                all_elevations.extend([None] * len(batch))
                progress.advance(task_id)

    return all_elevations


def get_altitude(lat: float, lon: float) -> float | None:
    """Get altitude for a single coordinate."""
    results = get_altitude_batch([(lat, lon)])
    return results[0] if results else None


def format_altitude(altitude: float | None) -> str:
    """Format altitude in meters with proper formatting."""
    if altitude is None:
        return "N/A"

    meters = int(round(altitude))
    return f"{meters:,}"
