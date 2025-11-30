"""Altitude/elevation API integration."""

from more_itertools import chunked

from src.core.logger import get_logger
from src.core.settings import settings
from src.services.client import APIClient

logger = get_logger(__name__)


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
