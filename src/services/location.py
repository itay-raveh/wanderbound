"""Service for fetching location data."""

from src.core.cache import cache_in_file
from src.core.logger import get_logger
from src.models.trip import Location
from src.services.client import APIClient

logger = get_logger(__name__)


@cache_in_file()
async def fetch_home_location() -> tuple[Location, str]:
    async with APIClient() as client:
        data = await client.get_json("http://ip-api.com/json/")
    return Location.model_validate(data), data["city"]
