"""Altitude/elevation API integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from more_itertools import chunked

from src.core.cache import cache_in_file
from src.core.logger import get_logger
from src.core.settings import settings

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.data.models import Step
    from src.services.client import APIClient


# OpenTopoData allows max 100 locations per request
_CHUK_SIZE = 100

logger = get_logger(__name__)


@cache_in_file()
async def fetch_all_altitudes(client: APIClient, steps: Sequence[Step]) -> list[float]:
    all_elevations: list[float] = []

    for batch in chunked(((step.location.lat, step.location.lon) for step in steps), _CHUK_SIZE):
        locations_param = "|".join([f"{lat},{lon}" for lat, lon in batch])
        url = settings.opentopodata_api_url.format(locations=locations_param)
        data: dict[str, list[dict[str, float]]] = await client.get_json(url)
        all_elevations += [result["elevation"] for result in data["results"]]

    return all_elevations
