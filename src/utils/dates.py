"""Date and time utility functions."""

from datetime import datetime

import pytz

__all__ = ["calculate_day_number"]


def calculate_day_number(
    step_start: float | None, trip_start: float | None, timezone_id: str
) -> int:
    if not step_start or not trip_start:
        return 0

    tz = pytz.timezone(timezone_id)
    step_dt = datetime.fromtimestamp(step_start, tz=tz)
    trip_dt = datetime.fromtimestamp(trip_start, tz=tz)

    delta = step_dt.date() - trip_dt.date()
    return delta.days + 1
