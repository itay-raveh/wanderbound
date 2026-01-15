"""Historical weather API integration for temperature data."""

from collections import Counter
from datetime import datetime, tzinfo

from pydantic import BaseModel

from src.core.cache import cache_in_file
from src.core.logger import get_logger
from src.core.settings import settings
from src.data.trip import Step, Weather
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
    hours: list[WeatherHourData] = []


class WeatherApiResponse(BaseModel):
    days: list[WeatherDayData] = []


def _normalize_icon_name(icon: str) -> str:
    return icon.lower().replace("_", "-")


def _find_night_hours(hours: list[WeatherHourData], tz: tzinfo) -> list[WeatherHourData]:
    night_hours: list[WeatherHourData] = []

    for hour_data in hours:
        hour = datetime.strptime(hour_data.datetime, "%H:%M:%S").astimezone(tz).hour
        if not 5 <= hour <= 21:
            night_hours.append(hour_data)

    return night_hours


def _get_night_icon(hours: list[WeatherHourData], tz: tzinfo, day_icon: str) -> str:
    if night_hours := _find_night_hours(hours, tz):
        icons = (hour.icon for hour in night_hours)
        common = Counter(icons).most_common()[0][0]
        return _normalize_icon_name(common)

    # fallback: convert day icon to night variant
    if day_icon == "clear":
        return "clear-night"
    if day_icon == "partly-cloudy":
        return "partly-cloudy-night"
    return day_icon.replace("-day", "-night")


@cache_in_file()
async def fetch_weather(client: APIClient, step: Step) -> Weather:
    data = WeatherApiResponse.model_validate(
        await client.get_json(
            settings.visual_crossing_api_url.format(
                lat=step.location.lat,
                lon=step.location.lon,
                date=step.date.strftime("%Y-%m-%d"),
                key=settings.visual_crossing_api_key,
            )
        )
    )

    day = data.days[0]
    day_icon = _normalize_icon_name(day.icon)
    return Weather(
        day_temp=day.tempmax,
        night_temp=day.tempmin,
        day_feels_like=day.feelslikemax,
        night_feels_like=day.feelslikemin,
        day_icon=day_icon,
        night_icon=_get_night_icon(day.hours, step.timezone, day_icon),
    )
