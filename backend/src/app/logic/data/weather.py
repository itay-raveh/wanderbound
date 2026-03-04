from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import aiohttp
from pydantic import BaseModel

from app.core.logging import config_logger
from app.core.settings import settings

if TYPE_CHECKING:
    from datetime import datetime

    from app.core.client import APIClient
    from app.models.polarsteps import PSStep

logger = config_logger(__name__)


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
    night_hours = [
        hour for hour in hours if not 5 <= int(hour.datetime[0:2]) <= 21
    ]

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


class Weather(BaseModel):
    day: WeatherData
    night: WeatherData | None = None

    @classmethod
    def from_step(cls, step: PSStep) -> Weather:
        return Weather(
            day=WeatherData(
                temp=step.weather_temperature,
                feels_like=step.weather_temperature,
                icon=step.weather_condition,
            )
        )


async def _fetch_weather(
    client: APIClient, lat: float, lon: float, date: datetime
) -> Weather:
    response = WeatherApiResponse.model_validate_json(
        await client.get(
            settings.visual_crossing_api_url.format(
                lat=lat,
                lon=lon,
                date=date.strftime("%Y-%m-%d"),
                key=settings.visual_crossing_api_key,
            )
        )
    )

    day = response.days[0]
    day_icon = _normalize_icon_name(day.icon)
    return Weather(
        day=WeatherData(
            temp=day.tempmax, feels_like=day.feelslikemax, icon=day_icon
        ),
        night=WeatherData(
            temp=day.tempmin,
            feels_like=day.feelslikemin,
            icon=_get_night_icon(day.hours, day_icon),
        ),
    )


async def fetch_weather(client: APIClient, step: PSStep) -> Weather:
    if not settings.visual_crossing_api_key:
        return Weather.from_step(step)

    try:
        return await _fetch_weather(
            client,
            round(step.location.lat, 2),
            round(step.location.lon, 2),
            step.datetime,
        )
    except aiohttp.ClientError:
        logger.exception(
            "Unable to fetch weather for %s at %s",
            step.location.detail,
            step.datetime,
        )
        return Weather.from_step(step)


class WeatherData(BaseModel):
    temp: float
    feels_like: float
    icon: str
