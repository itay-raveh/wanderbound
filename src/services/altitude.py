"""Altitude/elevation API integration."""

from more_itertools import chunked

from src.core.logger import get_logger
from src.core.settings import settings
from src.services.utils import APIClient

logger = get_logger(__name__)


async def get_altitudes(
    client: APIClient, locations: list[tuple[float, float]]
) -> list[float | None]:
    # We don't check cache here because the caller (batch fetching) should handle caching strategy
    # or we can rely on HTTP caching if the API supports it.
    # However, OpenTopoData is a GET request, so hishel will cache it if headers allow.
    # But individual point caching is tricky with batch requests.
    # For now, we'll rely on the fact that we're refactoring for better architecture.
    # If we need individual point caching, we should implement it at a higher level or
    # split requests (which might be slower/rate-limited).
    # Given the previous implementation did manual caching, we might want to preserve that
    # but `hishel` caches the *request*. If we request the same batch, it's cached.
    # If we request a subset, it's a new request.
    # For simplicity and robustness, we'll rely on hishel for the batch request caching.

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
