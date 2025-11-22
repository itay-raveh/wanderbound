"""API integrations for altitude, country maps, and flags."""

from .cache import get_cached, set_cached
from .altitude import get_altitude_batch, get_altitude, format_altitude
from .flags import get_country_flag_data_uri, extract_prominent_color_from_flag
from .maps import (
    get_country_map_svg,
    get_country_map_data_uri,
    get_country_map_dot_position,
)

__all__ = [
    "get_cached",
    "set_cached",
    "get_altitude_batch",
    "get_altitude",
    "format_altitude",
    "get_country_flag_data_uri",
    "extract_prominent_color_from_flag",
    "get_country_map_svg",
    "get_country_map_data_uri",
    "get_country_map_dot_position",
]
