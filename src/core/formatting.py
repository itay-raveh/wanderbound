"""Formatting utilities for coordinates, dates, and weather."""

import re
from datetime import datetime
from functools import lru_cache

import pytz
from geopy import Point

from src.core.logger import get_logger

logger = get_logger(__name__)

__all__ = ["format_coordinates", "format_date", "format_weather_condition"]


def format_coordinates(lat: float | None, lon: float | None) -> dict[str, str]:
    if lat is not None and not isinstance(lat, (int, float)):
        raise TypeError(f"lat must be numeric or None, got {type(lat).__name__}")
    if lon is not None and not isinstance(lon, (int, float)):
        raise TypeError(f"lon must be numeric or None, got {type(lon).__name__}")

    if lat is None or lon is None:
        return {"lat": "", "lon": ""}

    def _raise_format_error() -> None:
        raise ValueError("Unexpected format from geopy")

    try:
        point = Point(lat, lon)
        formatted = point.format_unicode()

        parts = formatted.split(", ")
        if len(parts) == 2:
            lat_part = parts[0].strip()
            lon_part = parts[1].strip()
        else:
            _raise_format_error()

        def round_seconds(dms_str: str) -> str:
            match = re.search(r'(\d+\.\d+)[″"]', dms_str)
            if match:
                seconds = round(float(match.group(1)))
                dms_str = re.sub(r"\d+\.\d+″", f"{seconds}″", dms_str)
                dms_str = re.sub(r'\d+\.\d+"', f'{seconds}"', dms_str)
            return dms_str.replace("\u2032", "'").replace("\u2033", '"')

        lat_dms = round_seconds(lat_part)
        lon_dms = round_seconds(lon_part)
    except (AttributeError, ValueError, TypeError):
        logger.exception(
            "Error formatting coordinates (%s, %s) with geopy. Using simplified format.", lat, lon
        )
        lat_dir = "N" if lat >= 0 else "S"
        lon_dir = "E" if lon >= 0 else "W"
        return {
            "lat": f"{abs(int(lat))}° {lat_dir}",
            "lon": f"{abs(int(lon))}° {lon_dir}",
        }
    else:
        return {"lat": lat_dms, "lon": lon_dms}


def format_date(timestamp: float | None, timezone_id: str) -> dict[str, str]:
    if not isinstance(timezone_id, str):
        raise TypeError(f"timezone_id must be a string, got {type(timezone_id).__name__}")

    if not timestamp:
        return {"month": "", "day": ""}

    try:
        tz = pytz.timezone(timezone_id)
        dt = datetime.fromtimestamp(timestamp, tz=tz)

        month = dt.strftime("%B").upper()
        day = str(dt.day)
    except (pytz.UnknownTimeZoneError, OSError, ValueError, OverflowError):
        logger.exception(
            "Error formatting date for timestamp %s in timezone %s", timestamp, timezone_id
        )
        try:
            tz = pytz.timezone(timezone_id)
            dt = datetime.fromtimestamp(timestamp, tz=tz)
            month_names = [
                "JANUARY",
                "FEBRUARY",
                "MARCH",
                "APRIL",
                "MAY",
                "JUNE",
                "JULY",
                "AUGUST",
                "SEPTEMBER",
                "OCTOBER",
                "NOVEMBER",
                "DECEMBER",
            ]
            month = month_names[dt.month - 1]
            day = str(dt.day)
        except (pytz.UnknownTimeZoneError, OSError, ValueError, OverflowError, IndexError):
            return {"month": "", "day": ""}
        else:
            return {"month": month, "day": day}
    else:
        return {"month": month, "day": day}


@lru_cache(maxsize=128)
def format_weather_condition(condition: str | None) -> str:
    if not condition:
        return "UNKNOWN"

    condition_map = {
        "clear-day": "CLEAR",
        "clear-night": "CLEAR",
        "rain": "RAIN",
        "snow": "SNOW",
        "sleet": "SLEET",
        "wind": "WIND",
        "fog": "FOG",
        "cloudy": "CLOUDY",
        "partly-cloudy-day": "PARTLY CLOUDY",
        "partly-cloudy-night": "PARTLY CLOUDY",
    }

    return condition_map.get(condition, condition.upper().replace("-", " "))
