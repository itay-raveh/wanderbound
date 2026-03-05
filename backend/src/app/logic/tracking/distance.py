import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.polarsteps import PSPoint


def distance_km_coords(p1_lon: float, p1_lat: float, p2_lon: float, p2_lat: float) -> float:
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(math.radians, [p1_lon, p1_lat, p2_lon, p2_lat])

    # haversine formula
    d_lon = lon2 - lon1
    d_lat = lat2 - lat1
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return c * 6371  # Radius of earth


def distance_km(p1: PSPoint, p2: PSPoint) -> float:
    return distance_km_coords(p1.lon, p1.lat, p2.lon, p2.lat)


def dist_time_speed(prev: PSPoint, curr: PSPoint) -> tuple[float, float, float]:
    dist_km = distance_km(prev, curr)
    time_h = (curr.time - prev.time) / 3600.0
    return dist_km, time_h, dist_km / time_h

