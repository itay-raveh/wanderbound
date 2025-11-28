"""Historical weather API integration for temperature data."""

import json
from datetime import datetime
from typing import Any

import httpx
import pytz
from dateutil import parser as date_parser
from pydantic import BaseModel

from src.core.logger import get_logger
from src.core.settings import settings

from .utils import (
    RateLimitError,
    fetch_and_cache_json_async,
    fetch_json_with_retry,
    get_cached,
    set_cached,
)

logger = get_logger(__name__)

# Visual Crossing API rate limit: 1000 requests/day = ~1 request per 86 seconds
# Using 0.2s minimum delay to allow for some burst while staying safe
API_CALLS_PER_SECOND = 5  # 5 calls per second = 0.2s between calls


class WeatherData(BaseModel):
    day_temp: float | None = None
    night_temp: float | None = None
    day_feels_like: float | None = None
    night_feels_like: float | None = None
    day_icon: str | None = None
    night_icon: str | None = None


def _normalize_icon_name(icon: str | None) -> str | None:
    if not icon:
        return None
    return icon.lower().replace("_", "-")


def _fetch_weather_data_with_retry(
    url: str, _lat: float, _lon: float, _date_str: str
) -> dict[str, Any]:
    """Fetch weather data from API with automatic retry on errors (but not 429)."""
    return fetch_json_with_retry(
        url,
        calls_per_second=API_CALLS_PER_SECOND,
        check_rate_limit=True,
        max_attempts=3,  # Explicitly set to 3 retries for non-429 errors
    )


def _find_night_hours(
    hours: list[dict[str, Any]], timezone: pytz.BaseTzInfo
) -> list[dict[str, Any]]:
    """Find hours that are nighttime (evening 20-23 or early morning 0-3)."""
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
    """Get night icon from night hours or fallback to day icon variant."""
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


def _parse_cached_weather_data(cached: dict[str, Any], tz: Any) -> WeatherData | None:
    """Parse cached weather data (either WeatherData dict or raw API response)."""
    # Check if it's a WeatherData dict from model_dump()
    if "day_temp" in cached or "day_icon" in cached:
        try:
            return WeatherData.model_validate(cached)
        except (ValueError, TypeError, KeyError) as e:
            logger.warning("Error parsing cached WeatherData: %s", e)
            return None

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
        logger.warning("Error parsing cached weather data: %s", e)

    return None


def _parse_day_weather_data(
    day_data: dict[str, Any],
) -> tuple[WeatherData, list[dict[str, Any]]]:
    """Parse day weather data from API response."""
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


def _build_weather_api_url(lat: float, lon: float, date_str: str) -> str:
    """Build Visual Crossing API URL."""
    elements = "tempmax,tempmin,feelslikemax,feelslikemin,icon"
    return settings.visual_crossing_api_url.format(
        location=f"{lat},{lon}",
        date=date_str,
        key=settings.visual_crossing_api_key,
        elements=elements,
    )


def _process_weather_api_response(
    data: dict[str, Any], tz: Any, lat: float, lon: float, date_str: str
) -> WeatherData:
    """Process API response and extract weather data."""
    weather = WeatherData()

    if "days" in data and len(data["days"]) > 0:
        day_data = data["days"][0]

        # Debug logging
        if logger.isEnabledFor(10):  # DEBUG level
            logger.debug(
                "Daily data fields:\nKeys: %s\nfeelslikemax: %s\nfeelslikemin: %s",
                list(day_data.keys()),
                day_data.get("feelslikemax"),
                day_data.get("feelslikemin"),
            )

        weather, hours = _parse_day_weather_data(day_data)

        # Process night icon from hourly data
        if hours:
            night_hours = _find_night_hours(hours, tz)
            weather.night_icon = _get_night_icon(night_hours, hours, weather.day_icon)

            # Debug logging for feels like temperatures
            if weather.day_feels_like is None and weather.night_feels_like is None:
                logger.debug(
                    "No feels like data for %s,%s on %s. feelslikemax: %s, feelslikemin: %s",
                    lat,
                    lon,
                    date_str,
                    day_data.get("feelslikemax"),
                    day_data.get("feelslikemin"),
                )

    return weather


def _check_weather_cache(cache_key: str) -> WeatherData | None:
    """Check cache for weather data."""
    cached_data = get_cached(cache_key)
    if cached_data is not None and isinstance(cached_data, dict):
        return WeatherData.model_validate(cached_data)
    return None


def _fetch_weather_data_safely(lat: float, lon: float, date_str: str) -> dict[str, Any] | None:
    """Fetch weather data from API with safety checks."""
    if not settings.visual_crossing_api_key:
        logger.warning(
            "No Visual Crossing API key configured. Set VISUAL_CROSSING_API_KEY "
            "environment variable to fetch temperatures. "
            "Get a free key at https://www.visualcrossing.com/weather-api"
        )
        return None

    url = _build_weather_api_url(lat, lon, date_str)

    try:
        data = _fetch_weather_data_with_retry(url, lat, lon, date_str)
    except RateLimitError:
        logger.warning("Rate limited (429) for %s,%s on %s. Skipping.", lat, lon, date_str)
        return None

    # Debug: Print full API response
    if logger.isEnabledFor(10):  # DEBUG level
        logger.debug(
            "Full API response for %s,%s on %s:\n%s",
            lat,
            lon,
            date_str,
            json.dumps(data, indent=2, default=str),
        )

    return data


def _handle_weather_errors(e: Exception) -> WeatherData:
    """Handle errors when fetching weather data."""
    if isinstance(e, httpx.HTTPStatusError):
        if e.response.status_code == 401:
            logger.warning(
                "Authentication failed for weather API. Please check your API key. Error: %s", e
            )
        else:
            logger.warning("HTTP error getting weather data: %s", e)
    elif isinstance(e, httpx.RequestError):
        logger.warning("Failed to get weather data: %s", e)
    elif isinstance(e, (KeyError, ValueError, TypeError)):
        logger.warning("Error parsing weather response: %s", e)

    return WeatherData()


def get_weather_data(lat: float, lon: float, timestamp: float, timezone_id: str) -> WeatherData:
    """Get day and night temperatures, feels like temperatures, and weather conditions."""
    # Convert timestamp to date in the location's timezone
    tz = pytz.timezone(timezone_id)
    dt = datetime.fromtimestamp(timestamp, tz=tz)
    date_str = dt.strftime("%Y-%m-%d")

    # Single cache key for all weather data
    cache_key = f"weather_{lat}_{lon}_{date_str}"

    # Check cache first
    cached_weather = _check_weather_cache(cache_key)
    if cached_weather is not None:
        return cached_weather

    default_weather = WeatherData()

    try:
        data = _fetch_weather_data_safely(lat, lon, date_str)
        if data is None:
            return default_weather

        weather = _process_weather_api_response(data, tz, lat, lon, date_str)

        # Cache using Pydantic's model_dump() for proper serialization
        set_cached(cache_key, weather.model_dump())

        if weather.day_temp is None and weather.night_temp is None:
            logger.debug("No weather data found for %s,%s on %s", lat, lon, date_str)
    except (httpx.HTTPStatusError, httpx.RequestError, KeyError, ValueError, TypeError) as e:
        return _handle_weather_errors(e)
    else:
        return weather


def get_temperatures(
    lat: float, lon: float, timestamp: float, timezone_id: str
) -> tuple[float | None, float | None]:
    """Get day and night temperatures for a location and date using Visual Crossing API."""
    weather = get_weather_data(lat, lon, timestamp, timezone_id)
    return (weather.day_temp, weather.night_temp)


def get_night_temperature(
    lat: float, lon: float, timestamp: float, timezone_id: str
) -> float | None:
    """Get night temperature for a location and date using Visual Crossing API."""
    _, night_temp = get_temperatures(lat, lon, timestamp, timezone_id)
    return night_temp


async def get_weather_data_async(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    timestamp: float,
    timezone_id: str,
) -> WeatherData:
    """Get day and night temperatures, feels like temperatures, and weather conditions (async)."""
    # Convert timestamp to date in the location's timezone
    tz = pytz.timezone(timezone_id)
    dt = datetime.fromtimestamp(timestamp, tz=tz)
    date_str = dt.strftime("%Y-%m-%d")

    # Single cache key for all weather data
    cache_key = f"weather_{lat}_{lon}_{date_str}"

    # Check cache first
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, dict):
        cached_weather = _parse_cached_weather_data(cached, tz)
        if cached_weather is not None:
            return cached_weather

    # Build API URL
    if not settings.visual_crossing_api_key:
        logger.warning(
            "No Visual Crossing API key configured. Set VISUAL_CROSSING_API_KEY "
            "environment variable to fetch temperatures. "
            "Get a free key at https://www.visualcrossing.com/weather-api"
        )
        return WeatherData()

    url = _build_weather_api_url(lat, lon, date_str)

    # Fetch with async helper
    data = await fetch_and_cache_json_async(
        client, cache_key, url, request_timeout=10.0, max_attempts=3
    )

    if not data:
        return WeatherData()

    try:
        weather = _process_weather_api_response(data, tz, lat, lon, date_str)

        # Cache using Pydantic's model_dump() for proper serialization
        set_cached(cache_key, weather.model_dump())
    except (KeyError, ValueError, TypeError) as e:
        logger.warning("Error parsing weather response: %s", e)
        return WeatherData()
    else:
        return weather
