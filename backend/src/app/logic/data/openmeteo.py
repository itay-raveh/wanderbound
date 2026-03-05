from __future__ import annotations

from itertools import batched
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable

    from app.core.client import RetryAsyncClient
    from app.models.polarsteps import Location


class OpenMeteoElevationsResponse(BaseModel):
    elevation: list[float]


async def fetch_elevations(
    client: RetryAsyncClient, locs: Iterable[Location]
) -> AsyncGenerator[float]:
    for batch in batched(locs, 100, strict=False):
        latitude = ",".join(str(loc.lat) for loc in batch)
        longitude = ",".join(str(loc.lon) for loc in batch)

        response = OpenMeteoElevationsResponse.model_validate_json(
            await client.get_with_retries(
                "https://api.open-meteo.com/v1/elevation",
                params={"latitude": latitude, "longitude": longitude},
            )
        )

        # Can't `yield from` in async :(
        for elevation in response.elevation:
            yield elevation
