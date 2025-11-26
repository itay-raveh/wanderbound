"""Coordinate formatting functions."""

import re

from geopy import Point

from ..logger import get_logger

logger = get_logger(__name__)

__all__ = ["format_coordinates"]


def format_coordinates(lat: float | None, lon: float | None) -> dict[str, str]:
    """Format coordinates into degrees, minutes, seconds.

    Args:
        lat: Latitude in decimal degrees, or None.
        lon: Longitude in decimal degrees, or None.

    Returns:
        Dictionary with 'lat' and 'lon' keys containing formatted strings.
        Empty strings if coordinates are None.

    Raises:
        TypeError: If lat or lon are provided but not numeric.
    """
    if lat is not None and not isinstance(lat, (int, float)):
        raise TypeError(f"lat must be numeric or None, got {type(lat).__name__}")
    if lon is not None and not isinstance(lon, (int, float)):
        raise TypeError(f"lon must be numeric or None, got {type(lon).__name__}")

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
        logger.warning(
            f"Error formatting coordinates ({lat}, {lon}) with geopy: {e}. "
            f"Using simplified format.",
            exc_info=True,
        )
        lat_dir = "N" if lat >= 0 else "S"
        lon_dir = "E" if lon >= 0 else "W"
        return {
            "lat": f"{abs(int(lat))}° {lat_dir}",
            "lon": f"{abs(int(lon))}° {lon_dir}",
        }
