"""API integrations for altitude, country maps, and flags."""

from .altitude import format_altitude, get_altitudes
from .client import APIClient
from .maps import get_country_map_dot_position, get_map_data
from .weather import get_weather_data

__all__ = [
    "APIClient",
    "format_altitude",
    "get_altitudes",
    "get_country_map_dot_position",
    "get_map_data",
    "get_weather_data",
]
