import logging
from collections.abc import Iterable, Sequence
from typing import Annotated

import httpx
from pydantic import BaseModel, BeforeValidator, ValidationError

from app.core.http import cached_client

from .types import HasLatLon

_client = cached_client(use_body_key=True)

PEAK_MIN_PROMINENCE = 300
PEAK_SEARCH_RADIUS = 500
PEAK_MAX_DEVIATION = 0.1

logger = logging.getLogger(__name__)


def _parse_ele(v: str | float) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    return float(v.replace(",", ".").split(";")[0].strip().rstrip("m "))


OSMElevation = Annotated[float, BeforeValidator(_parse_ele)]


class PeakTags(BaseModel):
    ele: OSMElevation
    name: str = ""


class PeakElement(BaseModel):
    tags: PeakTags


class OverpassResponse(BaseModel):
    elements: list[PeakElement]


def _local_peaks(dem_elevs: Sequence[float]) -> Iterable[int]:
    """Find steps that are local elevation maxima with meaningful prominence."""
    n = len(dem_elevs)
    for i in range(n):
        elev = dem_elevs[i]
        left = dem_elevs[i - 1] if i > 0 else 0
        right = dem_elevs[i + 1] if i < n - 1 else 0
        if elev - left >= PEAK_MIN_PROMINENCE and elev - right >= PEAK_MIN_PROMINENCE:
            yield i


async def correct_peaks(
    locs: Sequence[HasLatLon],
    elevs: Sequence[float],
) -> Sequence[float]:
    """Replace elevations with nearby OSM peak elevations where appropriate."""
    high_indices = list(_local_peaks(elevs))
    if not high_indices:
        return elevs

    high_locs = [locs[i] for i in high_indices]

    # Union of per-peak `around` queries (500m radius each)
    around_clauses = "".join(
        f'node["natural"="peak"]["ele"]'
        f"(around:{PEAK_SEARCH_RADIUS},{loc.lat},{loc.lon});"
        for loc in high_locs
    )
    query = f"[out:json][timeout:10];({around_clauses});out;"
    logger.debug("Overpass query for %d peaks: %s", len(high_indices), query)
    try:
        response = await _client.post(
            "https://overpass-api.de/api/interpreter", data={"data": query}
        )
        if response.status_code != 200:
            logger.warning(
                "Overpass returned %d: %s",
                response.status_code,
                response.text[:200],
            )
            return elevs
        osm = OverpassResponse.model_validate_json(response.content)
    except (httpx.HTTPError, ValidationError) as exc:
        logger.warning("Overpass peak query failed: %s", exc)
        return elevs

    logger.info(
        "Overpass returned %d elements for %d local peaks",
        len(osm.elements),
        len(high_indices),
    )
    if not osm.elements:
        return elevs

    # For each high-elevation step, pick the peak closest in elevation
    result = list(elevs)
    for i in high_indices:
        dem = elevs[i]
        best = min(osm.elements, key=lambda p: abs(p.tags.ele - dem))
        if best.tags.ele <= dem:
            continue
        deviation = (best.tags.ele - dem) / dem
        if deviation <= PEAK_MAX_DEVIATION:
            logger.info(
                "Corrected step %s: %dm -> %dm",
                best.tags.name or locs[i],
                int(dem),
                int(best.tags.ele),
            )
            result[i] = best.tags.ele

    return result
