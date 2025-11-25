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
        trip_path: Path to trip.json file. Must exist and be readable.

    Returns:
        TripData object with validated trip information.

    Raises:
        DataLoadError: If file cannot be read, JSON is invalid, or required
            fields are missing.
        TypeError: If trip_path is not a Path object.
    """
    if not isinstance(trip_path, Path):
        raise TypeError(f"trip_path must be a Path object, got {type(trip_path).__name__}")
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

    steps = []
    for step_data in data.get("all_steps", []):
        try:
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

    trip_data = TripData(**data)
    trip_data.all_steps = steps  # Replace with validated steps

    return trip_data


def get_step_photo_dir(trip_dir: Path, step: Step) -> Path | None:
    """Get the photo directory path for a step.

    Searches for photo directories matching common naming patterns:
    - {slug}_{step_id}/photos
    - {display_slug}_{step_id}/photos

    Args:
        trip_dir: Base trip directory containing step folders.
        step: Step object with slug and ID information.

    Returns:
        Path to the photo directory if found, None otherwise.
    """
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
    """Calculate the day number of the trip for a step.

    Computes the number of days from trip start to step start, accounting for
    timezone differences. Day 1 is the trip start date.

    Args:
        step_start: Unix timestamp of step start time, or None.
        trip_start: Unix timestamp of trip start time, or None.
        timezone_id: Timezone identifier (e.g., "America/New_York").

    Returns:
        Day number (1-indexed), or 0 if timestamps are invalid.
    """
    if not step_start or not trip_start:
        return 0

    tz = pytz.timezone(timezone_id)
    step_dt = datetime.fromtimestamp(step_start, tz=tz)
    trip_dt = datetime.fromtimestamp(trip_start, tz=tz)

    delta = step_dt.date() - trip_dt.date()
    return delta.days + 1


def get_steps_in_range(all_steps: list[Step], start: int, end: int) -> list[Step]:
    """Get steps within a specified range.

    Args:
        all_steps: Complete list of all steps in the trip.
        start: Start step number (1-indexed, inclusive).
        end: End step number (1-indexed, inclusive).

    Returns:
        List of Step objects within the specified range.
    """
    # Convert to 0-indexed
    start_idx = max(0, start - 1)
    end_idx = min(len(all_steps), end)
    return all_steps[start_idx:end_idx]


def get_steps_distributed(all_steps: list[Step], count: int) -> list[Step]:
    """Get evenly distributed steps across the entire trip.

    Samples steps at evenly spaced intervals to provide a representative
    view of the trip. Useful for testing or generating preview albums.

    Args:
        all_steps: Complete list of all steps in the trip.
        count: Number of steps to sample.

    Returns:
        List of Step objects evenly distributed across the trip.
        Returns all steps if count >= len(all_steps), or empty list if count <= 0.
    """
    if not all_steps or count <= 0:
        return []
    if count >= len(all_steps):
        return all_steps

    step_indices = []
    for i in range(count):
        idx = int((i / (count - 1)) * (len(all_steps) - 1)) if count > 1 else 0
        step_indices.append(idx)

    unique_indices = list(dict.fromkeys(step_indices))
    return [all_steps[idx] for idx in unique_indices]
