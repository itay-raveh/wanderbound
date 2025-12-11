"""Historical weather API integration for temperature data."""

import asyncio
from collections.abc import Callable
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from src.core.cache import cache_in_file
from src.core.logger import get_logger
from src.core.settings import settings
from src.data.models import Step, WeatherData
from src.services.client import APIClient

logger = get_logger(__name__)


class WeatherHourData(BaseModel):
    datetime: str
    icon: str


class WeatherDayData(BaseModel):
    tempmax: float | None = None
    tempmin: float | None = None
    feelslikemax: float | None = None
    feelslikemin: float | None = None
    icon: str | None = None
    hours: list[WeatherHourData] = []


class WeatherApiResponse(BaseModel):
    days: list[WeatherDayData] = []


def _normalize_icon_name(icon: str | None) -> str | None:
    if not icon:
        return None
    return icon.lower().replace("_", "-")


def _find_night_hours(hours: list[WeatherHourData], tz: tzinfo) -> list[WeatherHourData]:
    """Find hours that are nighttime (evening 20-23 or early morning 0-3)."""
    night_hours = []
    for hour_data in hours:
        hour_str = hour_data.datetime
        if not hour_str:
            continue

        try:
            dt = datetime.fromisoformat(hour_str).astimezone(tz)
        except (ValueError, TypeError, AttributeError):
            continue

        hour_num = dt.hour
        if hour_num >= 20 or hour_num < 4:
            night_hours.append(hour_data)

    return night_hours


def _get_night_icon(
    night_hours: list[WeatherHourData] | None,
    all_hours: list[WeatherHourData],
    day_icon: str | None,
) -> str | None:
    """Get night icon from night hours or fallback to day icon variant."""
    if night_hours:
        night_icon_raw = night_hours[0].icon
        return _normalize_icon_name(night_icon_raw)

    # Fallback: use last hour's icon
    if all_hours:
        last_hour_icon_raw = all_hours[-1].icon
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
    day_data: WeatherDayData,
) -> tuple[WeatherData, list[WeatherHourData]]:
    day_temp = day_data.tempmax
    night_temp = day_data.tempmin

    # Use feelslikemax and feelslikemin directly from daily data
    day_feels_like = day_data.feelslikemax
    night_feels_like = day_data.feelslikemin

    day_icon_raw = day_data.icon
    day_icon = _normalize_icon_name(day_icon_raw)

    hours = day_data.hours

    weather = WeatherData(
        day_temp=day_temp,
        night_temp=night_temp,
        day_feels_like=day_feels_like,
        night_feels_like=night_feels_like,
        day_icon=day_icon,
    )

    return weather, hours


def _parse_weather_api_response(data: WeatherApiResponse, tz: tzinfo) -> WeatherData:
    if not data.days:
        return WeatherData()

    day_data = data.days[0]
    weather, hours = _parse_day_weather_data(day_data)

    # Process night icon (from hourly data or fallback)
    night_hours = _find_night_hours(hours, tz)
    weather.night_icon = _get_night_icon(night_hours, hours, weather.day_icon)

    return weather


@cache_in_file()
async def _get_weather_data_cached(
    client: APIClient, lat: float, lon: float, date_str: str, timezone_id: str
) -> WeatherData:
    """Get weather data, cached by location and date."""
    url = settings.visual_crossing_api_url.format(
        lat=lat,
        lon=lon,
        date=date_str,
        key=settings.visual_crossing_api_key,
    )

    data = await client.get_json(url)
    return _parse_weather_api_response(
        WeatherApiResponse.model_validate(data), ZoneInfo(timezone_id)
    )


async def get_weather_data(
    client: APIClient,
    lat: float,
    lon: float,
    timestamp: float,
    timezone_id: str,
) -> WeatherData:
    # Convert timestamp to date in the location's timezone
    date_str = datetime.fromtimestamp(timestamp, tz=(ZoneInfo(timezone_id))).strftime("%Y-%m-%d")

    return await _get_weather_data_cached(client, lat, lon, date_str, timezone_id)


async def fetch_weather_data(
    client: APIClient, steps: list[Step], progress_callback: Callable[[int], None] | None = None
) -> list[WeatherData | None]:
    """Fetch weather data for all steps."""
    logger.debug("Fetching weather data...")

    tasks = []
    for _index, step in enumerate(steps):
        tasks.append(
            asyncio.create_task(
                get_weather_data(
                    client,
                    step.location.lat,
                    step.location.lon,
                    step.start_time,
                    step.timezone_id,
                )
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    if progress_callback:
        progress_callback(len(steps))

    weather_data: list[WeatherData | None] = []
    for i, res in enumerate(results):
        if isinstance(res, WeatherData):
            weather_data.append(res)
        else:
            weather_data.append(WeatherData())
            logger.warning("Failed to fetch weather for step %d", i)

    logger.debug("Fetched %d weather data entries", len(weather_data))
    return weather_data
