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
async def fetch_weather(
    client: APIClient,
    lat: float,
    lon: float,
    date: datetime,
    api_key: str | None = None,
) -> Weather:
    """Fetch weather from Visual Crossing API.

    Args:
        client: API client instance
        lat: Latitude
        lon: Longitude
        date: Date for historical weather
        api_key: Optional API key (uses settings.visual_crossing_api_key if not provided)

    """
    key = api_key or settings.visual_crossing_api_key
    if not key:
        msg = "No weather API key available"
        raise ValueError(msg)

    data = WeatherApiResponse.model_validate(
        await client.get_json(
            settings.visual_crossing_api_url.format(
                lat=lat,
                lon=lon,
                date=date.strftime("%Y-%m-%d"),
                key=key,
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


# Map Polarsteps conditions to meteocons icon names
_CONDITIONS_TO_ICON: dict[str, str] = {
    "sunny": "clear-day",
    "clear": "clear-day",
    "partly cloudy": "partly-cloudy-day",
    "cloudy": "cloudy",
    "overcast": "overcast",
    "rain": "rain",
    "rainy": "rain",
    "showers": "showers-day",
    "thunderstorm": "thunderstorms",
    "snow": "snow",
    "fog": "fog",
    "mist": "mist",
    "haze": "haze",
    "wind": "wind",
    "windy": "wind",
}


def weather_from_trip_data(temperature: float | None, conditions: str | None) -> Weather:
    """Create Weather from Polarsteps trip.json builtin weather data.

    Used as fallback when weather API is unavailable.
    """
    temp = temperature if temperature is not None else 20.0  # Default to 20°C

    # Map conditions to icon
    icon = "clear-day"  # Default
    if conditions:
        conditions_lower = conditions.lower()
        for key, value in _CONDITIONS_TO_ICON.items():
            if key in conditions_lower:
                icon = value
                break

    night_icon = icon.replace("-day", "-night") if "-day" in icon else icon

    return Weather(
        day_temp=temp,
        night_temp=temp - 5,  # Estimate night temp as 5°C cooler
        day_feels_like=temp,
        night_feels_like=temp - 5,
        day_icon=icon,
        night_icon=night_icon,
    )


async def get_weather_with_fallback(
    client: APIClient,
    lat: float,
    lon: float,
    date: datetime,
    trip_weather_temp: float | None = None,
    trip_weather_conditions: str | None = None,
    api_key: str | None = None,
) -> Weather:
    """Get weather using three-tier fallback strategy.

    Fallback order:
    1. API with user-provided key (if provided)
    2. API with builtin key (from settings)
    3. trip.json builtin weather data

    Args:
        client: API client instance
        lat: Latitude
        lon: Longitude
        date: Date for historical weather
        trip_weather_temp: Temperature from trip.json (fallback)
        trip_weather_conditions: Conditions from trip.json (fallback)
        api_key: Optional user-provided API key

    """
    # Tier 1 & 2: Try API (user key takes precedence via fetch_weather)
    effective_key = api_key or settings.visual_crossing_api_key
    if effective_key:
        try:
            return await fetch_weather(client, lat, lon, date, api_key=effective_key)
        except (ValueError, OSError) as e:
            logger.warning(
                "Weather API failed for %s, %s on %s (%s) - falling back to trip data",
                lat,
                lon,
                date.date(),
                e,
            )

    # Tier 3: Use trip.json builtin data
    logger.info("Using trip.json weather data for %s, %s", lat, lon)
    return weather_from_trip_data(trip_weather_temp, trip_weather_conditions)
