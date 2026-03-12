from __future__ import annotations

import asyncio
from itertools import batched
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.core.client import client
from app.core.logging import config_logger

from .types import HasLatLon

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

logger = config_logger(__name__)


class OpenMeteoElevationsResponse(BaseModel):
    elevation: list[float]


OPEN_METEO_MAX_PER_REQUEST = 100


async def elevations(
    locs: Sequence[HasLatLon],
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[float]:
    """Fetch elevations for a sequence of locations, with optional progress."""
    result: list[float] = []
    total = len(locs)
    for i, batch in enumerate(batched(locs, OPEN_METEO_MAX_PER_REQUEST, strict=False)):
        if i > 0:
            await asyncio.sleep(1)
        try:
            response = await client.get(
                "https://api.open-meteo.com/v1/elevation",
                params={
                    "latitude": ",".join(str(loc.lat) for loc in batch),
                    "longitude": ",".join(str(loc.lon) for loc in batch),
                    "model": "srtm_gl1",
                },
            )
        except Exception as e:
            msg = "Elevation API unavailable"
            raise RuntimeError(msg) from e
        if response.status_code != 200:
            msg = f"Elevation API returned {response.status_code}"
            raise RuntimeError(msg)
        parsed = OpenMeteoElevationsResponse.model_validate_json(await response.aread())
        result.extend(parsed.elevation)
        if on_progress:
            await on_progress(min(len(result), total), total)
    return result
