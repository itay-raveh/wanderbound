"""Date formatting functions."""

from datetime import datetime

import pytz

from src.core.logger import get_logger

logger = get_logger(__name__)

__all__ = ["format_date"]


def format_date(timestamp: float | None, timezone_id: str) -> dict[str, str]:
    """Format timestamp into month name and day.

    Args:
        timestamp: Unix timestamp, or None for empty date.
        timezone_id: Timezone identifier (e.g., 'America/New_York'). Must be valid.

    Returns:
        Dictionary with 'month' and 'day' keys. Empty strings if timestamp is None.

    Raises:
        TypeError: If timezone_id is not a string.
    """
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
