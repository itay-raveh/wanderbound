"""Historical weather API integration for temperature data."""

from datetime import datetime
from typing import Any

import httpx
import pytz
from dateutil import parser as date_parser
from pydantic import BaseModel

from ..logger import get_logger
from ..settings import get_settings
from .cache import get_cached, set_cached
from .helpers import fetch_and_cache_json_async
from .rate_limit import RateLimitError, fetch_json_with_retry

logger = get_logger(__name__)

# Visual Crossing API rate limit: 1000 requests/day = ~1 request per 86 seconds
# Using 0.2s minimum delay to allow for some burst while staying safe
API_CALLS_PER_SECOND = 5  # 5 calls per second = 0.2s between calls


class WeatherData(BaseModel):
    """Weather data for a location and date.

    Attributes:
        day_temp: Day temperature in Celsius (maximum temperature)
        night_temp: Night temperature in Celsius (minimum temperature)
        day_feels_like: "Feels like" temperature during the day in Celsius
        night_feels_like: "Feels like" temperature at night in Celsius
        day_icon: Icon name for basmilius weather-icons for day (e.g., "clear-day")
        night_icon: Icon name for basmilius weather-icons for night (e.g., "clear-night")
    """

    day_temp: float | None = None
    night_temp: float | None = None
    day_feels_like: float | None = None
    night_feels_like: float | None = None
    day_icon: str | None = None
    night_icon: str | None = None


def _normalize_icon_name(icon: str | None) -> str | None:
    """Normalize icon name to basmilius weather-icons format."""
    if not icon:
        return None
    return icon.lower().replace("_", "-")


def _fetch_weather_data_with_retry(
    url: str, lat: float, lon: float, date_str: str
) -> dict[str, Any]:
    """Fetch weather data from API with automatic retry on errors (but not 429).

    Args:
        url: API URL to fetch
        lat: Latitude (for logging)
        lon: Longitude (for logging)
        date_str: Date string (for logging)

    Returns:
        JSON response data

    Raises:
        RateLimitError: If rate limited (429) - this is NOT retried
        httpx.RequestError: On HTTP or network errors (these ARE retried)
    """
    return fetch_json_with_retry(
        url,
        calls_per_second=API_CALLS_PER_SECOND,
        check_rate_limit=True,
        max_attempts=3,  # Explicitly set to 3 retries for non-429 errors
    )


def _find_night_hours(
    hours: list[dict[str, Any]], timezone: pytz.BaseTzInfo
) -> list[dict[str, Any]]:
    """Find hours that are nighttime (evening 20-23 or early morning 0-3).

    Args:
        hours: List of hourly data dictionaries
        timezone: Timezone for parsing datetime

    Returns:
        List of night hour dictionaries
    """
    night_hours = []
    for hour_data in hours:
        hour_str = hour_data.get("datetime", "")
        if not hour_str:
            continue

        try:
            # Parse datetime string using dateutil.parser (handles various formats)
            # Visual Crossing API returns ISO format like "2024-01-15T14:00:00" or "14:00:00"
            dt = date_parser.parse(hour_str, default=datetime.now(timezone))
            # Ensure timezone-aware datetime
            dt = timezone.localize(dt) if dt.tzinfo is None else dt.astimezone(timezone)

            hour_num = dt.hour
            if hour_num >= 20 or hour_num < 4:
                night_hours.append(hour_data)
        except (ValueError, TypeError, AttributeError, date_parser.ParserError):
            continue

    return night_hours


def _get_night_icon(
    night_hours: list[dict[str, Any]] | None,
    all_hours: list[dict[str, Any]],
    day_icon: str | None,
) -> str | None:
    """Get night icon from night hours or fallback to day icon variant.

    Args:
        night_hours: List of night hour dictionaries, or None
        all_hours: All hourly data (for fallback)
        day_icon: Day icon name (for fallback conversion)

    Returns:
        Night icon name, or None if unavailable
    """
    if night_hours:
        night_icon_raw = night_hours[0].get("icon")
        return _normalize_icon_name(night_icon_raw)

    # Fallback: use last hour's icon
    if all_hours:
        last_hour_icon_raw = all_hours[-1].get("icon")
        night_icon = _normalize_icon_name(last_hour_icon_raw)
        if night_icon:
            return night_icon

    # Final fallback: convert day icon to night variant
    if day_icon:
        if "-day" in day_icon:
            return day_icon.replace("-day", "-night")
        if day_icon == "clear":
            return "clear-night"
        if day_icon == "partly-cloudy":
            return "partly-cloudy-night"

    return None


def _parse_day_weather_data(
    day_data: dict[str, Any],
) -> tuple[WeatherData, list[dict[str, Any]]]:
    """Parse day weather data from API response.

    Args:
        day_data: Daily weather data dictionary

    Returns:
        Tuple of (WeatherData with day data, hours list)
    """
    day_temp = day_data.get("tempmax")
    night_temp = day_data.get("tempmin")

    # Use feelslikemax and feelslikemin directly from daily data
    day_feels_like = day_data.get("feelslikemax")
    night_feels_like = day_data.get("feelslikemin")

    day_icon_raw = day_data.get("icon")
    day_icon = _normalize_icon_name(day_icon_raw)

    hours = day_data.get("hours", [])

    # Create WeatherData with day data (night data will be filled later)
    # Let Pydantic handle type conversions (int -> float, None handling, etc.)
    weather = WeatherData(
        day_temp=day_temp,
        night_temp=night_temp,
        day_feels_like=day_feels_like,
        night_feels_like=night_feels_like,
        day_icon=day_icon,
    )

    return (weather, hours)


def get_weather_data(lat: float, lon: float, timestamp: float, timezone_id: str) -> WeatherData:
    """Get day and night temperatures, feels like temperatures, and weather conditions.

    Args:
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
    cached_data = get_cached(cache_key)
    if cached_data is not None and isinstance(cached_data, dict):
        return WeatherData.model_validate(cached_data)

    try:
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

        try:
            data = _fetch_weather_data_with_retry(url, lat, lon, date_str)
        except RateLimitError:
            # 429 errors are not retried - skip immediately
            logger.warning(f"Rate limited (429) for {lat},{lon} on {date_str}. Skipping.")
            return WeatherData()

        # Debug: Print full API response for first call to inspect structure
        if logger.isEnabledFor(10):  # DEBUG level
            import json

            logger.debug(
                f"Full API response for {lat},{lon} on {date_str}:\n"
                f"{json.dumps(data, indent=2, default=str)}"
            )

        # Extract weather data from API response
        weather = WeatherData()

        if "days" in data and len(data["days"]) > 0:
            day_data = data["days"][0]

            # Debug: Print daily data fields
            if logger.isEnabledFor(10):  # DEBUG level
                logger.debug(
                    f"Daily data fields for {lat},{lon} on {date_str}:\n"
                    f"Keys: {list(day_data.keys())}\n"
                    f"feelslikemax: {day_data.get('feelslikemax')}\n"
                    f"feelslikemin: {day_data.get('feelslikemin')}"
                )

            weather, hours = _parse_day_weather_data(day_data)

            # Process night icon from hourly data (feels like is already set from daily data)
            if hours:
                night_hours = _find_night_hours(hours, tz)
                weather.night_icon = _get_night_icon(night_hours, hours, weather.day_icon)

                # Debug logging for feels like temperatures
                if weather.day_feels_like is None and weather.night_feels_like is None:
                    logger.debug(
                        f"No feels like data for {lat},{lon} on {date_str}. "
                        f"feelslikemax: {day_data.get('feelslikemax')}, "
                        f"feelslikemin: {day_data.get('feelslikemin')}"
                    )

        # Cache using Pydantic's model_dump() for proper serialization
        set_cached(cache_key, weather.model_dump())

        if weather.day_temp is None and weather.night_temp is None:
            logger.debug(f"No weather data found for {lat},{lon} on {date_str}")

        return weather

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            logger.warning(
                f"Authentication failed for weather API. Please check your API key. Error: {e}"
            )
        else:
            logger.warning(f"HTTP error getting weather data: {e}")
        return WeatherData()
    except httpx.RequestError as e:
        logger.warning(f"Failed to get weather data: {e}")
        return WeatherData()
    except (KeyError, ValueError, TypeError) as e:
        logger.warning(f"Error parsing weather response: {e}")
        return WeatherData()


def get_temperatures(
    lat: float, lon: float, timestamp: float, timezone_id: str
) -> tuple[float | None, float | None]:
    """Get day and night temperatures for a location and date using Visual Crossing API.

    Args:
        lat: Latitude
        lon: Longitude
        timestamp: Unix timestamp for the date
        timezone_id: Timezone ID (e.g., "America/New_York")

    Returns:
        Tuple of (day_temp, night_temp) in Celsius, or (None, None) if unavailable
    """
    weather = get_weather_data(lat, lon, timestamp, timezone_id)
    return (weather.day_temp, weather.night_temp)


def get_night_temperature(
    lat: float, lon: float, timestamp: float, timezone_id: str
) -> float | None:
    """Get night temperature for a location and date using Visual Crossing API.

    Args:
        lat: Latitude
        lon: Longitude
        timestamp: Unix timestamp for the date
        timezone_id: Timezone ID (e.g., "America/New_York")

    Returns:
        Night temperature in Celsius, or None if unavailable
    """
    _, night_temp = get_temperatures(lat, lon, timestamp, timezone_id)
    return night_temp


def get_weather_data_batch(
    locations_with_dates: list[tuple[float, float, float, str]],
) -> list[WeatherData]:
    """Get weather data for multiple locations and dates.

    Args:
        locations_with_dates: List of (lat, lon, timestamp, timezone_id) tuples

    Returns:
        List of WeatherData objects. If rate limited (429), remaining items will be empty WeatherData.
    """
    results: list[WeatherData] = []

    for lat, lon, timestamp, timezone_id in locations_with_dates:
        try:
            weather_data = get_weather_data(lat, lon, timestamp, timezone_id)
            results.append(weather_data)
        except RateLimitError:
            # On 429, stop processing and return empty WeatherData for remaining items
            logger.warning(
                f"Rate limited (429) for weather API. Skipping remaining {len(locations_with_dates) - len(results)} requests."
            )
            # Fill remaining with empty WeatherData
            results.extend([WeatherData()] * (len(locations_with_dates) - len(results)))
            break

    return results


def get_night_temperature_batch(
    locations_with_dates: list[tuple[float, float, float, str]],
) -> list[float | None]:
    """Get night temperatures for multiple locations and dates.

    Args:
        locations_with_dates: List of (lat, lon, timestamp, timezone_id) tuples

    Returns:
        List of night temperatures in Celsius, or None for unavailable data
    """
    results: list[float | None] = []

    for lat, lon, timestamp, timezone_id in locations_with_dates:
        temp = get_night_temperature(lat, lon, timestamp, timezone_id)
        results.append(temp)
        # Rate limiting is handled by @limits decorator on _fetch_weather_data_with_retry

    return results


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
