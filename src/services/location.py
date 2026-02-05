"""Service for fetching location data."""

from src.core.cache import async_cache
from src.core.logger import get_logger
from src.models.trip import Location
from src.services.client import APIClient

logger = get_logger(__name__)


@async_cache
async def fetch_home_location() -> tuple[Location, str]:
    async with APIClient() as client:
        data = await client.get_json("http://ip-api.com/json/")
    return Location.model_validate(data), data.get("city", "Unknown")
