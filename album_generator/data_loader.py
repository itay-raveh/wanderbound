"""Load and parse trip data from JSON files using Pydantic models."""

import json
from datetime import datetime
from pathlib import Path

import pytz

from .exceptions import DataLoadError
from .logger import get_logger
from .models import Location, Step, TripData

logger = get_logger(__name__)

__all__ = [
    "load_trip_data",
    "get_step_photo_dir",
    "calculate_day_number",
    "get_steps_in_range",
    "get_steps_distributed",
]


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
    except FileNotFoundError as e:
        raise DataLoadError(
            f"Trip file not found at {trip_path}. Please ensure the file exists.",
            file_path=str(trip_path),
        ) from e
    except json.JSONDecodeError as e:
        raise DataLoadError(
            f"Invalid JSON in trip file {trip_path}: {e}. "
            f"Please check that the file is valid JSON.",
            file_path=str(trip_path),
        ) from e

    if not isinstance(data, dict):
        raise DataLoadError(
            f"Trip data must be a JSON object, got {type(data).__name__}",
            file_path=str(trip_path),
        )

    if "all_steps" not in data:
        raise DataLoadError(
            f"Trip data missing required 'all_steps' field. "
            f"Please check that {trip_path} contains valid trip data.",
            file_path=str(trip_path),
        )

    if not isinstance(data.get("all_steps"), list):
        raise DataLoadError(
            f"Trip data 'all_steps' must be a list, got {type(data.get('all_steps')).__name__}",
            file_path=str(trip_path),
        )

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
            step_id = step_data.get("id", "unknown")
            logger.warning(
                f"Failed to parse step {step_id} in {trip_path}: {e}. "
                f"Skipping this step and continuing with others.",
                exc_info=True,
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

    # Calculate step indices to sample evenly across the trip
    step_indices = []
    for i in range(count):
        idx = int((i / (count - 1)) * (len(all_steps) - 1)) if count > 1 else 0
        step_indices.append(idx)

    # Remove duplicates while preserving order using dict.fromkeys()
    unique_indices = list(dict.fromkeys(step_indices))
    return [all_steps[idx] for idx in unique_indices]
