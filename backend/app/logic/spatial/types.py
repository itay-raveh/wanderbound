from typing import Protocol

type Lat = float
type Lon = float


class HasLatLon(Protocol):
    lat: Lat
    lon: Lon
