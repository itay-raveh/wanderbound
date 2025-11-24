"""Altitude/elevation API integration."""

import time

import requests
from more_itertools import chunked

from ..logger import get_logger
from ..settings import get_settings
from .cache import _get_elevation_cache

logger = get_logger(__name__)


def get_altitude_batch(locations: list[tuple[float, float]]) -> list[float | None]:
    """Get altitude for multiple coordinates using OpenTopoData API with batching."""
    elevation_cache = _get_elevation_cache()

    all_elevations: list[float | None] = []
    locations_to_query: list[tuple[float, float]] = []

    for loc in locations:
        lat, lon = loc
        key = f"{lat},{lon}"
        cached_value = elevation_cache.get(key, default=None)
        if cached_value is not None:
            all_elevations.append(cached_value)
        else:
            locations_to_query.append(loc)

    max_locations_per_request = 100
    max_calls_per_day = 1000
    calls_made = 0

    for batch in chunked(locations_to_query, max_locations_per_request):
        if calls_made >= max_calls_per_day:
            logger.warning(
                "Reached maximum API calls for today. Using cached data only."
            )
            all_elevations.extend([None] * len(batch))
            continue

        locations_param = "|".join([f"{lat},{lon}" for lat, lon in batch])
        settings = get_settings()
        url = f"{settings.opentopodata_api_url}?locations={locations_param}"

        try:
            logger.debug(
                f"Fetching elevation for batch of {len(batch)} locations (call {calls_made + 1})"
            )
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if "results" in data:
                for loc, result in zip(batch, data["results"], strict=True):
                    lat, lon = loc
                    elevation = result.get("elevation")
                    all_elevations.append(elevation)

                    key = f"{lat},{lon}"
                    elevation_cache.set(key, elevation)
                logger.debug(f"Cached {len(batch)} elevations")
            else:
                logger.warning("No results in elevation API response for batch")
                all_elevations.extend([None] * len(batch))

            calls_made += 1
            time.sleep(1)

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get elevation for batch: {e}")
            all_elevations.extend([None] * len(batch))
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing elevation response: {e}", exc_info=True)
            all_elevations.extend([None] * len(batch))

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
