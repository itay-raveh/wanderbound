"""Altitude/elevation API integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from more_itertools import chunked

from psagen.core.cache import async_cache
from psagen.core.logger import create_progress, get_logger
from psagen.core.settings import settings

if TYPE_CHECKING:
    from collections.abc import Sequence

    from psagen.logic.client import APIClient


# OpenTopoData allows max 100 locations per request
_CHUNK_SIZE = 100

logger = get_logger(__name__)


@async_cache
async def fetch_all_altitudes(
    client: APIClient, points: Sequence[tuple[float, float]]
) -> list[float]:
    all_elevations: list[float] = []

    with create_progress() as progress:
        for batch in chunked(progress.track(points, description="Altitudes..."), _CHUNK_SIZE):
            locations_param = "|".join(f"{lat},{lon}" for lat, lon in batch)
            url = settings.opentopodata_api_url.format(locations=locations_param)
            data: dict[str, list[dict[str, float]]] = await client.get_json(url)
            all_elevations += [result["elevation"] for result in data["results"]]

    return all_elevations
