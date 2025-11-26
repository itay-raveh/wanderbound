"""Date and time utility functions."""

from datetime import datetime

import pytz

__all__ = ["calculate_day_number"]


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
