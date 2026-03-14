from itertools import batched
from typing import TYPE_CHECKING

from pydantic import BaseModel

from . import client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from app.logic.spatial.types import HasLatLon


class _ElevationResult(BaseModel):
    elevation: list[float]


OPEN_METEO_MAX_PER_REQUEST = 100


async def elevations(locs: Sequence[HasLatLon]) -> AsyncIterator[float]:
    for batch in batched(locs, OPEN_METEO_MAX_PER_REQUEST, strict=False):
        response = await client.get(
            "https://api.open-meteo.com/v1/elevation",
            params={
                "latitude": ",".join(str(loc.lat) for loc in batch),
                "longitude": ",".join(str(loc.lon) for loc in batch),
                "model": "srtm_gl1",
            },
        )
        response.raise_for_status()

        result = _ElevationResult.model_validate_json(response.content)

        for elev in result.elevation:
            yield elev
