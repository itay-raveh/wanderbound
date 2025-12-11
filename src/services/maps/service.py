"""Main map service entry point."""

from __future__ import annotations

import asyncio
from asyncio.locks import Lock
from typing import TYPE_CHECKING

import geopandas as gpd
from geopandas import GeoDataFrame

from src.core.cache import cache_in_file
from src.core.logger import get_logger
from src.core.settings import settings
from src.data.models import MapData, Step

from .coordinates import get_country_map_dot_position
from .generator import generate_geo_calibrated_svg

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.services.client import APIClient

logger = get_logger(__name__)

_NE_GEOJSON = "ne_50m_admin_0_countries.geojson"

_NE_FETCH_LOCK = Lock()


async def _load_natural_earth_data(client: APIClient) -> GeoDataFrame:
    """Load Natural Earth GeoJSON data from cache or download it."""
    geojson_file = settings.cache_dir / _NE_GEOJSON

    if geojson_file.exists():
        try:
            return await asyncio.to_thread(gpd.read_file, str(geojson_file))
        except Exception as e:  # noqa: BLE001
            logger.warning("Cached map data corrupt, re-downloading: %s", e)

    logger.info("Downloading Natural Earth 50m data...")

    content = await client.get_content(settings.natural_earth_geojson_url + _NE_GEOJSON)
    geojson_file.write_bytes(content)

    return await asyncio.to_thread(gpd.read_file, str(geojson_file))


@cache_in_file()
async def _get_map_data(
    client: APIClient,
    country_code: str,
    lat: float,
    lon: float,
) -> MapData:
    """Get country map SVG and dot position."""
    # Only one of the tasks needs to fetch the ne dataset,
    # the rest should wait for it, and then they can simply use the local file.
    await _NE_FETCH_LOCK.acquire()
    world = await _load_natural_earth_data(client)
    _NE_FETCH_LOCK.release()

    svg_data = generate_geo_calibrated_svg(world, country_code)
    dot_position = get_country_map_dot_position(lon, lat, svg_data)

    return MapData(
        svg_content=svg_data,
        dot_position=dot_position,
    )


async def fetch_maps(
    client: APIClient, steps: list[Step], progress_callback: Callable[[int], None]
) -> list[MapData | None]:
    """Fetch maps and calculate dot positions for all steps."""

    async def _get_map_data_and_progress(step: Step) -> MapData:
        map_data = await _get_map_data(
            client,
            step.location.country_code,
            step.location.lat,
            step.location.lon,
        )
        progress_callback(1)
        return map_data

    results = await asyncio.gather(
        *(_get_map_data_and_progress(step) for step in steps),
        return_exceptions=True,
    )

    map_results: list[MapData | None] = []
    for i, res in enumerate(results):
        if isinstance(res, MapData):
            map_results.append(res)
        else:
            map_results.append(None)
            logger.warning("Failed to fetch map for step %d: %s", i, res)

    logger.debug("Processed %d maps", len(map_results))
    return map_results
