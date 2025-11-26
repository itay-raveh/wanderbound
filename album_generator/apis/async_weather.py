"""Async weather API integration using httpx."""

from datetime import datetime

import httpx
import pytz

from ..logger import get_logger
from ..settings import get_settings
from .async_helpers import fetch_and_cache_json_async
from .cache import get_cached, set_cached
from .weather import WeatherData, _find_night_hours, _get_night_icon, _parse_day_weather_data

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
        # Cache might be a dict (raw API response) or a WeatherData dict (from model_dump)
        # Check if it's a WeatherData dict (has day_temp, night_temp, etc.)
        if "day_temp" in cached or "day_icon" in cached:
            # It's a WeatherData dict from model_dump()
            try:
                return WeatherData.model_validate(cached)
            except Exception as e:
                logger.warning(f"Error parsing cached WeatherData: {e}")
        else:
            # It's a raw API response dict
            try:
                days = cached.get("days", [])
                if days:
                    day_data = days[0]
                    weather, hours = _parse_day_weather_data(day_data)
                    # Process night icon from hourly data
                    if hours:
                        night_hours = _find_night_hours(hours, tz)
                        weather.night_icon = _get_night_icon(night_hours, hours, weather.day_icon)
                    return weather
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Error parsing cached weather data: {e}")

    # Build API URL
    settings = get_settings()

    if not settings.visual_crossing_api_key:
        logger.warning(
            "No Visual Crossing API key configured. Set VISUAL_CROSSING_API_KEY "
            "environment variable to fetch temperatures. "
            "Get a free key at https://www.visualcrossing.com/weather-api"
        )
        return WeatherData()

    # Visual Crossing API (free tier: 1000 records/day)
    # Request only the daily fields we need to minimize record cost:
    # - tempmax, tempmin (temperatures)
    # - feelslikemax, feelslikemin (for feels like temperatures)
    # - icon (weather condition)
    # Note: include=hours is needed for night icon, but we can't
    # specify which hourly fields to return, so all hourly fields will be included
    elements = "tempmax,tempmin,feelslikemax,feelslikemin,icon"
    url = settings.visual_crossing_api_url.format(
        location=f"{lat},{lon}",
        date=date_str,
        key=settings.visual_crossing_api_key,
        elements=elements,
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
            night_hours = _find_night_hours(hours, tz)
            weather.night_icon = _get_night_icon(night_hours, hours, weather.day_icon)

        # Cache using Pydantic's model_dump() for proper serialization
        set_cached(cache_key, weather.model_dump())

        return weather
    except (KeyError, ValueError, TypeError) as e:
        logger.warning(f"Error parsing weather response: {e}")
        return WeatherData()
