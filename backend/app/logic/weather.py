from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.core.client import client
from app.core.logging import config_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from app.models.trips import PSStep

logger = config_logger(__name__)

_WMO_DAY: dict[int, str] = {
    0: "clear-day",
    1: "clear-day",
    2: "partly-cloudy-day",
    3: "overcast-day",
    45: "fog-day",
    48: "fog-day",
    51: "partly-cloudy-day-drizzle",
    53: "drizzle",
    55: "drizzle",
    56: "partly-cloudy-day-sleet",
    57: "sleet",
    61: "partly-cloudy-day-rain",
    63: "rain",
    65: "rain",
    66: "partly-cloudy-day-sleet",
    67: "sleet",
    71: "partly-cloudy-day-snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "partly-cloudy-day-rain",
    81: "rain",
    82: "thunderstorms-day-rain",
    85: "partly-cloudy-day-snow",
    86: "snow",
    95: "thunderstorms-day",
    96: "thunderstorms-day-rain",
    99: "thunderstorms-day-rain",
}

_WMO_NIGHT: dict[int, str] = {
    0: "clear-night",
    1: "clear-night",
    2: "partly-cloudy-night",
    3: "overcast-night",
    45: "fog-night",
    48: "fog-night",
    51: "partly-cloudy-night-drizzle",
    53: "drizzle",
    55: "drizzle",
    56: "partly-cloudy-night-sleet",
    57: "sleet",
    61: "partly-cloudy-night-rain",
    63: "rain",
    65: "rain",
    66: "partly-cloudy-night-sleet",
    67: "sleet",
    71: "partly-cloudy-night-snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "partly-cloudy-night-rain",
    81: "rain",
    82: "thunderstorms-night-rain",
    85: "partly-cloudy-night-snow",
    86: "snow",
    95: "thunderstorms-night",
    96: "thunderstorms-night-rain",
    99: "thunderstorms-night-rain",
}


class WeatherData(BaseModel):
    temp: float
    feels_like: float
    icon: str


class Weather(BaseModel):
    day: WeatherData
    night: WeatherData | None = None


def _wmo_icon(code: int, *, night: bool = False) -> str:
    table = _WMO_NIGHT if night else _WMO_DAY
    return table.get(code, "not-available")


_DAILY_FIELDS = (
    "temperature_2m_max,"
    "temperature_2m_min,"
    "apparent_temperature_max,"
    "apparent_temperature_min,"
    "weather_code"
)


class _DailyData(BaseModel):
    time: list[str]
    temperature_2m_max: list[float]
    temperature_2m_min: list[float]
    apparent_temperature_max: list[float]
    apparent_temperature_min: list[float]
    weather_code: list[int]


class _LocationResult(BaseModel):
    daily: _DailyData


_WEATHER_CONCURRENCY = 10


def _weather_from_result(
    step: PSStep,
    loc: _LocationResult,
) -> Weather | None:
    """Extract weather for a specific step's date from a location result."""
    date_str = str(step.datetime.date())
    try:
        day_idx = loc.daily.time.index(date_str)
    except ValueError:
        return None
    wmo_code = loc.daily.weather_code[day_idx]
    d = loc.daily
    return Weather(
        day=WeatherData(
            temp=d.temperature_2m_max[day_idx],
            feels_like=d.apparent_temperature_max[day_idx],
            icon=_wmo_icon(wmo_code),
        ),
        night=WeatherData(
            temp=d.temperature_2m_min[day_idx],
            feels_like=d.apparent_temperature_min[day_idx],
            icon=_wmo_icon(wmo_code, night=True),
        ),
    )


async def _fetch_one(
    step: PSStep,
    sem: asyncio.Semaphore,
) -> Weather:
    """Fetch weather for a single step.  Raises on failure."""
    date_str = str(step.datetime.date())
    async with sem:
        try:
            response = await client.get(
                "https://archive-api.open-meteo.com/v1/archive",
                params={
                    "latitude": round(step.location.lat, 2),
                    "longitude": round(step.location.lon, 2),
                    "start_date": date_str,
                    "end_date": date_str,
                    "daily": _DAILY_FIELDS,
                    "timezone": "auto",
                },
            )
        except Exception as e:
            msg = f"Weather API unavailable for {step.location.detail}"
            raise RuntimeError(msg) from e
        if response.status_code != 200:
            msg = (
                f"Weather API returned {response.status_code}"
                f" for {step.location.detail}"
            )
            raise RuntimeError(msg)
        result = _LocationResult.model_validate(response.json())
        weather = _weather_from_result(step, result)
        if weather is None:
            msg = f"No weather data for {step.location.detail} on {date_str}"
            raise RuntimeError(msg)
        return weather


async def build_weathers(
    steps: Sequence[PSStep],
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[Weather]:
    """Fetch weather for all steps.  Raises on any failure."""
    sem = asyncio.Semaphore(_WEATHER_CONCURRENCY)
    total = len(steps)
    completed = 0

    async def _one(step: PSStep) -> Weather:
        nonlocal completed
        weather = await _fetch_one(step, sem)
        completed += 1
        if on_progress:
            await on_progress(completed, total)
        return weather

    return list(await asyncio.gather(*(_one(s) for s in steps)))
