"""API integrations for altitude, country maps, and flags."""

from .altitude import format_altitude, get_altitudes
from .flags import extract_prominent_color_from_flag, get_flag_data
from .maps import get_country_map_dot_position, get_map_data
from .utils import APIClient
from .weather import get_weather_data

__all__ = [
    "APIClient",
    "extract_prominent_color_from_flag",
    "format_altitude",
    "get_altitudes",
    "get_country_map_dot_position",
    "get_flag_data",
    "get_map_data",
    "get_weather_data",
]
