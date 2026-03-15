from typing import Annotated, Protocol

from pydantic import StringConstraints

type Lat = float
type Lon = float

CountryCode = Annotated[str, StringConstraints(to_lower=True, pattern="[a-zA-Z]{2}|00")]
HexColor = Annotated[str, StringConstraints(to_lower=True, pattern="#[0-9a-fA-F]{6}")]


class HasLatLon(Protocol):
    lat: Lat
    lon: Lon
