from __future__ import annotations

from itertools import batched
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable

    from app.core.client import APIClient
    from app.models.polarsteps import PSLocation


class OpenMeteoElevationsResponse(BaseModel):
    elevation: list[float]


async def fetch_elevations(
    client: APIClient, locs: Iterable[PSLocation]
) -> AsyncGenerator[float]:
    for batch in batched(locs, 100, strict=False):
        latitude = ",".join(str(loc.lat) for loc in batch)
        longitude = ",".join(str(loc.lon) for loc in batch)

        response = OpenMeteoElevationsResponse.model_validate_json(
            await client.get(
                f"https://api.open-meteo.com/v1/elevation?{latitude=!s}&{longitude=!s}",
            )
        )

        # Can't `yield from` in async :(
        for elevation in response.elevation:
            yield elevation
