from __future__ import annotations

from typing import TYPE_CHECKING

from more_itertools import chunked
from pydantic import BaseModel

from psagen.core.cache import async_cache
from psagen.core.logger import get_logger
from psagen.core.settings import settings

if TYPE_CHECKING:
    from collections.abc import Sequence

    from psagen.core.client import APIClient


# OpenTopoData allows max 100 locations per request
_CHUNK_SIZE = 100

logger = get_logger(__name__)


class OpenTopoResult(BaseModel):
    elevation: float


class OpenTopoResponse(BaseModel):
    results: list[OpenTopoResult]


@async_cache
async def fetch_all_altitudes(
    client: APIClient, points: Sequence[tuple[float, float]]
) -> list[float]:
    all_elevations: list[float] = []

    for batch in chunked(points, _CHUNK_SIZE):
        locations_param = "|".join(f"{lat},{lon}" for lat, lon in batch)
        url = settings.opentopodata_api_url.format(locations=locations_param)
        response = OpenTopoResponse.model_validate_json(await client.get(url))
        all_elevations += [result.elevation for result in response.results]

    return all_elevations
