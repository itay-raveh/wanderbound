from __future__ import annotations

from itertools import batched
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

from app.core.client import client

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable

    from app.models.trips import Location


class OpenMeteoElevationsResponse(BaseModel):
    elevation: list[float]


OPEN_METEO_MAX_PER_REQUEST = 100


class Point(Protocol):
    lat: float
    lon: float


async def elevations(locs: Iterable[Location]) -> AsyncGenerator[float]:
    for batch in batched(locs, OPEN_METEO_MAX_PER_REQUEST, strict=False):
        response = await client.get(
            "https://api.open-meteo.com/v1/elevation",
            params={
                "latitude": ",".join(str(loc.lat) for loc in batch),
                "longitude": ",".join(str(loc.lon) for loc in batch),
            },
        )
        result = OpenMeteoElevationsResponse.model_validate_json(await response.aread())

        # Can't `yield from` in async :(
        for elevation in result.elevation:
            yield elevation
