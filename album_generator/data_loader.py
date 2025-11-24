"""Load and parse trip data from JSON files using Pydantic models."""

import json
from datetime import datetime
from pathlib import Path

import pytz
from geopy import Point

from .exceptions import DataLoadError
from .logger import get_logger
from .models import Location, Step, TripData

logger = get_logger(__name__)


def load_trip_data(trip_path: Path) -> TripData:
    """Load trip data from trip.json file and validate with Pydantic.

    Args:
        trip_path: Path to trip.json file

    Returns:
        TripData object with validated trip information

    Raises:
        DataLoadError: If file cannot be read or JSON is invalid
    """
    try:
        data = json.loads(trip_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise DataLoadError(
            f"Failed to load trip data from {trip_path}: {e}",
            file_path=str(trip_path),
        ) from e

    # Parse steps with Pydantic - let Pydantic handle validation
    steps = []
    for step_data in data.get("all_steps", []):
        try:
            # Handle location data - Pydantic will validate required fields
            if "location" in step_data and step_data["location"]:
                step_data["location"] = Location(**step_data["location"])

            step = Step(**step_data)
            steps.append(step)
        except (KeyError, TypeError, ValueError) as e:
            # Log error but continue with other steps
            logger.warning(
                f"Failed to parse step {step_data.get('id')}: {e}", exc_info=True
            )
            continue

    # Create TripData model - let Pydantic handle defaults
    trip_data = TripData(**data)
    trip_data.all_steps = steps  # Replace with validated steps

    return trip_data


def get_step_photo_dir(trip_dir: Path, step: Step) -> Path | None:
    """Get the photo directory for a step."""
    slug = step.slug or step.display_slug or ""

    if not slug:
        return None

    # Try both patterns: slug_id and display_slug_id
    patterns = [
        f"{slug}_{step.id}",
        f"{step.display_slug or slug}_{step.id}",
    ]

    for pattern in patterns:
        photo_dir = trip_dir / pattern / "photos"
        if photo_dir.exists():
            return photo_dir

    return None


def format_date(timestamp: float | None, timezone_id: str) -> dict[str, str]:
    """Format timestamp into month name and day using built-in datetime formatting."""
    if not timestamp:
        return {"month": "", "day": ""}

    try:
        tz = pytz.timezone(timezone_id)
        dt = datetime.fromtimestamp(timestamp, tz=tz)

        # Format month name in uppercase using strftime
        month = dt.strftime("%B").upper()
        day = str(dt.day)

        return {"month": month, "day": day}
    except Exception as e:
        logger.warning(f"Error formatting date: {e}", exc_info=True)
        # Fallback to manual formatting
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


def calculate_day_number(
    step_start: float | None, trip_start: float | None, timezone_id: str
) -> int:
    """Calculate the day number of the trip for a step."""
    if not step_start or not trip_start:
        return 0

    tz = pytz.timezone(timezone_id)
    step_dt = datetime.fromtimestamp(step_start, tz=tz)
    trip_dt = datetime.fromtimestamp(trip_start, tz=tz)

    delta = step_dt.date() - trip_dt.date()
    return delta.days + 1


def format_coordinates(lat: float | None, lon: float | None) -> dict[str, str]:
    """Format coordinates into degrees, minutes, seconds using geopy."""
    if lat is None or lon is None:
        return {"lat": "", "lon": ""}

    try:
        point = Point(lat, lon)
        # Format using format_unicode which gives us the degree symbol format
        # Returns format like "37° 46′ 29.64″ N, 122° 25′ 9.84″ W"
        formatted = point.format_unicode()

        # Split into latitude and longitude parts
        parts = formatted.split(", ")
        if len(parts) == 2:
            lat_part = parts[0].strip()
            lon_part = parts[1].strip()
        else:
            # Fallback if format is unexpected
            raise ValueError("Unexpected format from geopy")

        # Round seconds to integer and convert unicode primes to regular quotes
        import re

        def round_seconds(dms_str: str) -> str:
            # Match pattern: number″ (using unicode prime) or number" (regular quote)
            match = re.search(r'(\d+\.\d+)[″"]', dms_str)
            if match:
                seconds = int(round(float(match.group(1))))
                # Replace both unicode and regular quote versions
                dms_str = re.sub(r"\d+\.\d+″", f"{seconds}″", dms_str)
                dms_str = re.sub(r'\d+\.\d+"', f'{seconds}"', dms_str)
            # Convert unicode primes to regular quotes for consistency
            dms_str = dms_str.replace("°", "°").replace("′", "'").replace("″", '"')
            return dms_str

        lat_dms = round_seconds(lat_part)
        lon_dms = round_seconds(lon_part)

        return {"lat": lat_dms, "lon": lon_dms}
    except (AttributeError, ValueError, TypeError) as e:
        # Fallback to simple format if geopy fails
        logger.warning(f"Error formatting coordinates with geopy: {e}", exc_info=True)
        lat_dir = "N" if lat >= 0 else "S"
        lon_dir = "E" if lon >= 0 else "W"
        return {
            "lat": f"{abs(int(lat))}° {lat_dir}",
            "lon": f"{abs(int(lon))}° {lon_dir}",
        }


def format_weather_condition(condition: str | None) -> str:
    """Format weather condition code to display text."""
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


def get_steps_in_range(all_steps: list[Step], start: int, end: int) -> list[Step]:
    """Get steps in the specified range (1-indexed, inclusive)."""
    # Convert to 0-indexed
    start_idx = max(0, start - 1)
    end_idx = min(len(all_steps), end)
    return all_steps[start_idx:end_idx]


def get_steps_distributed(all_steps: list[Step], count: int) -> list[Step]:
    """Get evenly distributed steps across the entire trip."""
    if not all_steps or count <= 0:
        return []
    if count >= len(all_steps):
        return all_steps

    # Calculate step indices to sample
    step_indices = []
    for i in range(count):
        idx = int((i / (count - 1)) * (len(all_steps) - 1)) if count > 1 else 0
        step_indices.append(idx)

    # Remove duplicates while preserving order
    seen = set()
    result = []
    for idx in step_indices:
        if idx not in seen:
            seen.add(idx)
            result.append(all_steps[idx])

    return result
