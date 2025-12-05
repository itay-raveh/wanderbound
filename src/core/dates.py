from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from src.data.models import Step, TripData


def _format_date_range(start: datetime, end: datetime) -> str:
    """Format date range smartly, omitting redundant year/month."""
    if start.year == end.year:
        if start.month == end.month:
            # Same month and year: "16 - 26 April 2025"
            return f"{start.day} - {end.day} {start.strftime('%B %Y')}"
        # Different month, same year: "16 April - 2 May 2025"
        return f"{start.day} {start.strftime('%B')} - {end.day} {end.strftime('%B %Y')}"

    # Different year: "28 December 2024 - 15 January 2025"
    return f"{start.day} {start.strftime('%B %Y')} - {end.day} {end.strftime('%B %Y')}"


def get_display_date_range(trip: TripData, steps: list[Step] | None) -> str | None:
    """Calculate and format the display date range for the trip."""
    tz = ZoneInfo(trip.timezone_id)

    if steps:
        start_ts = min(s.start_time for s in steps)
        end_ts = max(s.start_time for s in steps)

        # If last step has end_time, use it
        last_step = max(steps, key=lambda s: s.start_time)
        if last_step.end_time:
            end_ts = last_step.end_time

        start_dt = datetime.fromtimestamp(start_ts, tz=tz)
        end_dt = datetime.fromtimestamp(end_ts, tz=tz)

        return _format_date_range(start_dt, end_dt)

    if trip.start_date and trip.end_date:
        start_dt = datetime.fromtimestamp(trip.start_date, tz=tz)
        end_dt = datetime.fromtimestamp(trip.end_date, tz=tz)
        return _format_date_range(start_dt, end_dt)

    return None
