"""Service for fetching location data."""

from psagen.core.cache import async_cache
from psagen.core.logger import get_logger
from psagen.logic.client import APIClient
from psagen.models.trip import Location

logger = get_logger(__name__)


@async_cache
async def fetch_home_location() -> tuple[Location, str]:
    async with APIClient() as client:
        data = await client.get_json("http://ip-api.com/json/")
    return Location.model_validate(data), data.get("city", "Unknown")
