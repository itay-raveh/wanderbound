"""Altitude/elevation API integration."""

from typing import TYPE_CHECKING

from more_itertools import chunked

from src.core.cache import cache_in_file
from src.core.logger import get_logger
from src.core.settings import settings
from src.services.client import APIClient

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.data.models import Step

logger = get_logger(__name__)


@cache_in_file()
async def get_altitudes(
    client: APIClient, locations: list[tuple[float, float]]
) -> list[float | None]:
    all_elevations: list[float | None] = []

    # OpenTopoData allows max 100 locations per request
    max_locations_per_request = 100

    for batch in chunked(locations, max_locations_per_request):
        locations_param = "|".join([f"{lat},{lon}" for lat, lon in batch])
        url = settings.opentopodata_api_url.format(locations=locations_param)

        try:
            data = await client.get_json(url)

            if "results" in data:
                for result in data["results"]:
                    elevation_raw = result.get("elevation")
                    elevation: float | None = (
                        float(elevation_raw)
                        if elevation_raw is not None and isinstance(elevation_raw, (int, float))
                        else None
                    )
                    all_elevations.append(elevation)
            else:
                logger.warning("No results in elevation API response for batch")
                all_elevations.extend([None] * len(batch))

        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to get elevation for batch: %s", e)
            all_elevations.extend([None] * len(batch))

    return all_elevations


def format_altitude(altitude: float | None) -> str:
    if altitude is None:
        return "N/A"

    meters = round(altitude)
    return f"{meters:,}"


async def fetch_altitudes(
    client: APIClient,
    steps: list["Step"],
    progress_callback: "Callable[[int], None] | None" = None,
) -> list[float | None]:
    """Fetch altitudes for all steps in batches."""
    logger.debug("Fetching altitudes...")

    locations = [(step.location.lat, step.location.lon) for step in steps]

    elevations = await get_altitudes(client, locations)

    if progress_callback:
        progress_callback(len(steps))

    logger.debug("Fetched %d altitudes", len(elevations))
    return elevations
