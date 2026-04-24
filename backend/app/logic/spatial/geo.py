"""Scalar geodesic utilities."""

from math import atan2, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0

type Coords = list[tuple[float, float]]  # [lon, lat] GeoJSON order


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two (lat, lon) points."""
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * atan2(sqrt(a), sqrt(1 - a))


def total_length_km(coords: Coords) -> float:
    """Total length of a coordinate list in km. Coords are (lon, lat) GeoJSON order."""
    return sum(
        haversine_km(coords[i][1], coords[i][0], coords[i + 1][1], coords[i + 1][0])
        for i in range(len(coords) - 1)
    )
