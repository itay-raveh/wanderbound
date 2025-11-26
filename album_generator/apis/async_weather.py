"""Async weather API integration using httpx."""

from datetime import datetime

import httpx
import pytz

from ..logger import get_logger
from ..settings import get_settings
from .async_helpers import fetch_and_cache_json_async
from .cache import get_cached
from .weather import WeatherData, _parse_day_weather_data

logger = get_logger(__name__)

# Visual Crossing API rate limit: 1000 requests/day = ~1 request per 86 seconds
# Using 5 calls per second to allow for some burst while staying safe
API_CALLS_PER_SECOND = 5


async def get_weather_data_async(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    timestamp: float,
    timezone_id: str,
) -> WeatherData:
    """Get day and night temperatures, feels like temperatures, and weather conditions (async).

    Args:
        client: httpx AsyncClient instance
        lat: Latitude
        lon: Longitude
        timestamp: Unix timestamp for the date
        timezone_id: Timezone ID (e.g., "America/New_York")

    Returns:
        WeatherData object containing temperatures, feels like temperatures, and icons
    """
    # Convert timestamp to date in the location's timezone
    tz = pytz.timezone(timezone_id)
    dt = datetime.fromtimestamp(timestamp, tz=tz)
    date_str = dt.strftime("%Y-%m-%d")

    # Single cache key for all weather data
    cache_key = f"weather_{lat}_{lon}_{date_str}"

    # Check cache first
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, dict):
        try:
            weather, hours = _parse_day_weather_data(cached)
            # Process night icon from hourly data
            if hours:
                tz = pytz.timezone(timezone_id)
                from .weather import _find_night_hours, _get_night_icon

                night_hours = _find_night_hours(hours, tz)
                weather.night_icon = _get_night_icon(night_hours, hours, weather.day_icon)
            return weather
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Error parsing cached weather data: {e}")

    # Build API URL
    settings = get_settings()
    url = settings.visual_crossing_api_url.format(
        lat=lat, lon=lon, date=date_str, api_key=settings.visual_crossing_api_key
    )

    # Fetch with async helper
    data = await fetch_and_cache_json_async(client, cache_key, url, timeout=10.0, max_attempts=3)

    if not data:
        return WeatherData()

    try:
        # Parse response similar to synchronous version
        days = data.get("days", [])
        if not days:
            return WeatherData()

        day_data = days[0]
        weather, hours = _parse_day_weather_data(day_data)

        # Process night icon from hourly data
        if hours:
            tz = pytz.timezone(timezone_id)
            from .weather import _find_night_hours, _get_night_icon

            night_hours = _find_night_hours(hours, tz)
            weather.night_icon = _get_night_icon(night_hours, hours, weather.day_icon)

        return weather
    except (KeyError, ValueError, TypeError) as e:
        logger.warning(f"Error parsing weather response: {e}")
        return WeatherData()
