"""Historical weather API integration for temperature data."""

from datetime import datetime
from typing import Any

import pytz
from dateutil import parser as date_parser

from src.core.logger import get_logger
from src.core.settings import settings
from src.data.models import WeatherData, WeatherResult
from src.services.utils import APIClient

logger = get_logger(__name__)


def _normalize_icon_name(icon: str | None) -> str | None:
    if not icon:
        return None
    return icon.lower().replace("_", "-")


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


async def get_weather_data(  # noqa: PLR0913
    client: APIClient,
    lat: float,
    lon: float,
    timestamp: float,
    timezone_id: str,
    step_index: int,
) -> WeatherResult:
    """Get weather data for a location and time."""
    if not settings.visual_crossing_api_key:
        return WeatherResult(step_index=step_index, data=None)

    # Convert timestamp to date in the location's timezone
    tz = pytz.timezone(timezone_id)
    dt = datetime.fromtimestamp(timestamp, tz=tz)
    date_str = dt.strftime("%Y-%m-%d")

    elements = "tempmax,tempmin,feelslikemax,feelslikemin,icon"
    url = settings.visual_crossing_api_url.format(
        location=f"{lat},{lon}",
        date=date_str,
        key=settings.visual_crossing_api_key,
        elements=elements,
    )

    try:
        data = await client.get_json(url)
        weather = _process_weather_api_response(data, tz, lat, lon, date_str)
        return WeatherResult(step_index=step_index, data=weather)
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to get weather data for step %d: %s", step_index, e)
        return WeatherResult(step_index=step_index, data=None)


__all__ = ["WeatherData", "get_weather_data"]
