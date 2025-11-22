"""Load and parse trip data from JSON files using Pydantic models."""

import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime
import pytz

from .models import TripData, Step, Location


def load_trip_data(trip_path: Path) -> TripData:
    """Load trip data from trip.json file and validate with Pydantic."""
    with open(trip_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Parse steps with Pydantic - let Pydantic handle validation
    steps = []
    for step_data in data.get("all_steps", []):
        try:
            # Handle location data - Pydantic will validate required fields
            if "location" in step_data and step_data["location"]:
                step_data["location"] = Location(**step_data["location"])

            step = Step(**step_data)
            steps.append(step)
        except Exception as e:
            # Log error but continue with other steps
            print(f"Warning: Failed to parse step {step_data.get('id')}: {e}")
            continue

    # Create TripData model - let Pydantic handle defaults
    trip_data = TripData(**data)
    trip_data.all_steps = steps  # Replace with validated steps

    return trip_data


def get_step_photo_dir(trip_dir: Path, step: Step) -> Optional[Path]:
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


def format_date(timestamp: Optional[float], timezone_id: str) -> dict[str, str]:
    """Format timestamp into month name and day with ordinal."""
    if not timestamp:
        return {"month": "", "day": ""}

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
    day = dt.day

    return {"month": month, "day": str(day)}


def calculate_day_number(
    step_start: Optional[float], trip_start: Optional[float], timezone_id: str
) -> int:
    """Calculate the day number of the trip for a step."""
    if not step_start or not trip_start:
        return 0

    tz = pytz.timezone(timezone_id)
    step_dt = datetime.fromtimestamp(step_start, tz=tz)
    trip_dt = datetime.fromtimestamp(trip_start, tz=tz)

    delta = step_dt.date() - trip_dt.date()
    return delta.days + 1


def format_coordinates(lat: Optional[float], lon: Optional[float]) -> dict[str, str]:
    """Format coordinates into degrees, minutes, seconds."""
    if lat is None or lon is None:
        return {"lat": "", "lon": ""}

    def dms(coord: float, is_lat: bool) -> str:
        abs_coord = abs(coord)
        degrees = int(abs_coord)
        minutes = int((abs_coord - degrees) * 60)
        seconds = int(((abs_coord - degrees) * 60 - minutes) * 60)

        direction = (
            "N"
            if (is_lat and coord >= 0)
            else "S" if is_lat else ("E" if coord >= 0 else "W")
        )
        return f"{degrees}° {minutes}' {seconds}\" {direction}"

    return {"lat": dms(lat, True), "lon": dms(lon, False)}


def format_weather_condition(condition: Optional[str]) -> str:
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


def get_steps_in_range(all_steps: List[Step], start: int, end: int) -> List[Step]:
    """Get steps in the specified range (1-indexed, inclusive)."""
    # Convert to 0-indexed
    start_idx = max(0, start - 1)
    end_idx = min(len(all_steps), end)
    return all_steps[start_idx:end_idx]


def get_steps_distributed(all_steps: List[Step], count: int) -> List[Step]:
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
