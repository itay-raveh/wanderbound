"""Load and parse trip data from JSON files using Pydantic models."""

import json
from pathlib import Path

from .exceptions import DataLoadError
from .logger import get_logger
from .models import Location, Step, TripData

logger = get_logger(__name__)

__all__ = ["load_trip_data"]


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
            if step_data.get("location"):
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
