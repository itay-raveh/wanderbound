"""Formatting functions for dates, coordinates, and weather conditions."""

from datetime import datetime

import pytz
from geopy import Point

from .logger import get_logger

logger = get_logger(__name__)


def format_date(timestamp: float | None, timezone_id: str) -> dict[str, str]:
    """Format timestamp into month name and day.

    Args:
        timestamp: Unix timestamp
        timezone_id: Timezone identifier (e.g., 'America/New_York')

    Returns:
        Dictionary with 'month' and 'day' keys
    """
    if not timestamp:
        return {"month": "", "day": ""}

    try:
        tz = pytz.timezone(timezone_id)
        dt = datetime.fromtimestamp(timestamp, tz=tz)

        month = dt.strftime("%B").upper()
        day = str(dt.day)

        return {"month": month, "day": day}
    except Exception as e:
        logger.warning(f"Error formatting date: {e}", exc_info=True)
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
            return {"month": month, "day": day}
        except Exception:
            return {"month": "", "day": ""}


def format_coordinates(lat: float | None, lon: float | None) -> dict[str, str]:
    """Format coordinates into degrees, minutes, seconds.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        Dictionary with 'lat' and 'lon' keys containing formatted strings
    """
    if lat is None or lon is None:
        return {"lat": "", "lon": ""}

    try:
        point = Point(lat, lon)
        formatted = point.format_unicode()

        parts = formatted.split(", ")
        if len(parts) == 2:
            lat_part = parts[0].strip()
            lon_part = parts[1].strip()
        else:
            raise ValueError("Unexpected format from geopy")

        import re

        def round_seconds(dms_str: str) -> str:
            match = re.search(r'(\d+\.\d+)[″"]', dms_str)
            if match:
                seconds = int(round(float(match.group(1))))
                dms_str = re.sub(r"\d+\.\d+″", f"{seconds}″", dms_str)
                dms_str = re.sub(r'\d+\.\d+"', f'{seconds}"', dms_str)
            dms_str = dms_str.replace("°", "°").replace("′", "'").replace("″", '"')
            return dms_str

        lat_dms = round_seconds(lat_part)
        lon_dms = round_seconds(lon_part)

        return {"lat": lat_dms, "lon": lon_dms}
    except (AttributeError, ValueError, TypeError) as e:
        logger.warning(f"Error formatting coordinates with geopy: {e}", exc_info=True)
        lat_dir = "N" if lat >= 0 else "S"
        lon_dir = "E" if lon >= 0 else "W"
        return {
            "lat": f"{abs(int(lat))}° {lat_dir}",
            "lon": f"{abs(int(lon))}° {lon_dir}",
        }


def format_weather_condition(condition: str | None) -> str:
    """Format weather condition code to display text.

    Args:
        condition: Weather condition code (e.g., 'clear-day', 'rain')

    Returns:
        Formatted weather condition string in uppercase
    """
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
