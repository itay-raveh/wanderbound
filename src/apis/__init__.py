"""API integrations for altitude, country maps, and flags."""

from .altitude import format_altitude, get_altitude, get_altitude_batch
from .cache import get_cached, set_cached
from .flags import extract_prominent_color_from_flag
from .maps import (
    get_country_map_dot_position,
    get_country_map_svg,
)

__all__ = [
    "extract_prominent_color_from_flag",
    "format_altitude",
    "get_altitude",
    "get_altitude_batch",
    "get_cached",
    "get_country_map_dot_position",
    "get_country_map_svg",
    "set_cached",
]
