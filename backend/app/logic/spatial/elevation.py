from __future__ import annotations

import asyncio
from itertools import batched
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.core.client import client
from app.core.logging import config_logger

from .types import HasLatLon

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable

logger = config_logger(__name__)


class OpenMeteoElevationsResponse(BaseModel):
    elevation: list[float]


OPEN_METEO_MAX_PER_REQUEST = 100


async def elevations(locs: Iterable[HasLatLon]) -> AsyncGenerator[float]:
    for i, batch in enumerate(batched(locs, OPEN_METEO_MAX_PER_REQUEST, strict=False)):
        if i > 0:
            await asyncio.sleep(1)
        response = await client.get(
            "https://api.open-meteo.com/v1/elevation",
            params={
                "latitude": ",".join(str(loc.lat) for loc in batch),
                "longitude": ",".join(str(loc.lon) for loc in batch),
                "model": "srtm_gl1",
            },
        )
        result = OpenMeteoElevationsResponse.model_validate_json(await response.aread())

        for elev in result.elevation:
            yield elev
