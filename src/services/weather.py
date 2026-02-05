"""Historical weather API integration for temperature data."""

from collections import Counter
from datetime import datetime

from pydantic import BaseModel

from src.core.cache import async_cache
from src.core.logger import get_logger
from src.core.settings import settings
from src.models.trip import Weather
from src.services.client import APIClient

logger = get_logger(__name__)


class WeatherHourData(BaseModel):
    datetime: str
    icon: str


class WeatherDayData(BaseModel):
    tempmax: float
    tempmin: float
    feelslikemax: float
    feelslikemin: float
    icon: str
    hours: list[WeatherHourData]


class WeatherApiResponse(BaseModel):
    days: list[WeatherDayData] = []


def _normalize_icon_name(icon: str) -> str:
    return icon.lower().replace("_", "-")


def _get_night_icon(hours: list[WeatherHourData], day_icon: str) -> str:
    night_hours = [hour for hour in hours if not 5 <= int(hour.datetime[0:2]) <= 21]

    if night_hours:
        icons = (hour.icon for hour in night_hours)
        if common := Counter(icons).most_common(1):
            return _normalize_icon_name(common[0][0])

    # fallback: convert day icon to night variant
    if day_icon == "clear":
        return "clear-night"
    if day_icon == "partly-cloudy":
        return "partly-cloudy-night"
    return day_icon.replace("-day", "-night")


@async_cache
async def fetch_weather(client: APIClient, lat: float, lon: float, date: datetime) -> Weather:
    data = WeatherApiResponse.model_validate(
        await client.get_json(
            settings.visual_crossing_api_url.format(
                lat=lat,
                lon=lon,
                date=date.strftime("%Y-%m-%d"),
                key=settings.visual_crossing_api_key,
            )
        )
    )

    if not data.days:
        logger.warning("No weather data found for %s at %s, %s", date, lat, lon)
        return Weather(
            day_temp=0,
            night_temp=0,
            day_feels_like=0,
            night_feels_like=0,
            day_icon="unknown",
            night_icon="unknown",
        )

    day = data.days[0]
    day_icon = _normalize_icon_name(day.icon)
    return Weather(
        day_temp=day.tempmax,
        night_temp=day.tempmin,
        day_feels_like=day.feelslikemax,
        night_feels_like=day.feelslikemin,
        day_icon=day_icon,
        night_icon=_get_night_icon(day.hours, day_icon),
    )
