"""Open-Meteo API client: DEM elevations and historical weather.

Both endpoints share an IP-based rate limit (480/min). Rate limiting
sits between the cache and network layers so cache hits bypass it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from itertools import batched
from typing import TYPE_CHECKING, Protocol

import httpx
from aiolimiter import AsyncLimiter
from httpx import AsyncBaseTransport, AsyncHTTPTransport, Request, Response
from pydantic import BaseModel

from app.core.http import cached_client
from app.models.weather import Weather, WeatherData

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from app.models.polarsteps import HasLatLon


class _HasLocationDetail(Protocol):
    lat: float
    lon: float
    detail: str


class _StepLike(Protocol):
    """Structural interface for step objects used by the weather API."""

    @property
    def location(self) -> _HasLocationDetail: ...
    @property
    def datetime(self) -> datetime: ...


class _RateLimitedTransport(AsyncBaseTransport):
    """Rate-limits on cache miss only.

    For the elevation API each coordinate in the batch counts as one call,
    so the weight is derived from the comma-separated ``latitude`` param.
    """

    def __init__(self, limiter: AsyncLimiter) -> None:
        self._transport = AsyncHTTPTransport()
        self._limiter = limiter

    async def handle_async_request(self, request: Request) -> Response:
        weight = 1
        lat = request.url.params.get("latitude", "")
        if "," in lat:
            weight = lat.count(",") + 1
        await self._limiter.acquire(weight)
        return await self._transport.handle_async_request(request)


# Free tier: 600 calls/min, 5 000/hr.  We stay under with 480/min.
_limiter = AsyncLimiter(480, 60)

_client = cached_client(transport=_RateLimitedTransport(limiter=_limiter))


class _ElevationResult(BaseModel):
    elevation: list[float]


OPEN_METEO_MAX_PER_REQUEST = 100


async def elevations(locs: Sequence[HasLatLon]) -> AsyncIterator[float]:
    for batch in batched(locs, OPEN_METEO_MAX_PER_REQUEST, strict=False):
        response = await _client.get(
            "https://api.open-meteo.com/v1/elevation",
            params={
                "latitude": ",".join(str(loc.lat) for loc in batch),
                "longitude": ",".join(str(loc.lon) for loc in batch),
                "model": "srtm_gl1",
            },
        )
        response.raise_for_status()

        result = _ElevationResult.model_validate_json(response.content)

        for elev in result.elevation:
            yield elev


_WMO_ICONS: dict[int, str] = {
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


def _wmo_icon(code: int, *, night: bool = False) -> str:
    icon = _WMO_ICONS.get(code, "not-available")
    return icon.replace("-day", "-night") if night else icon


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


def _weather_from_result(step: _StepLike, loc: _LocationResult) -> Weather | None:
    """Extract weather for a specific step's date from a location result."""
    date_str = str(step.datetime.date())
    try:
        day_idx = loc.daily.time.index(date_str)
    except ValueError:
        return None
    wmo_code = loc.daily.weather_code[day_idx]
    return Weather(
        day=WeatherData(
            temp=loc.daily.temperature_2m_max[day_idx],
            feels_like=loc.daily.apparent_temperature_max[day_idx],
            icon=_wmo_icon(wmo_code),
        ),
        night=WeatherData(
            temp=loc.daily.temperature_2m_min[day_idx],
            feels_like=loc.daily.apparent_temperature_min[day_idx],
            icon=_wmo_icon(wmo_code, night=True),
        ),
    )


async def _fetch_one(step: _StepLike) -> Weather:
    """Fetch weather for a single step.  Raises on failure."""
    date_str = str(step.datetime.date())
    try:
        response = await _client.get(
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
    except httpx.HTTPError as e:
        msg = f"Weather API unavailable for {step.location.detail}"
        raise RuntimeError(msg) from e
    if response.status_code != 200:
        msg = f"Weather API returned {response.status_code} for {step.location.detail}"
        raise RuntimeError(msg)
    result = _LocationResult.model_validate_json(response.content)
    weather = _weather_from_result(step, result)
    if weather is None:
        msg = f"No weather data for {step.location.detail} on {date_str}"
        raise RuntimeError(msg)
    return weather


async def build_weathers(
    steps: Sequence[_StepLike],
) -> AsyncIterator[tuple[int, Weather]]:
    """Yield (index, weather) as each completes (concurrent, unordered)."""

    async def _one(idx: int, step: _StepLike) -> tuple[int, Weather]:
        return idx, await _fetch_one(step)

    for coro in asyncio.as_completed([_one(i, s) for i, s in enumerate(steps)]):
        yield await coro
