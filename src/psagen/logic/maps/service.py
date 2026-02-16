from __future__ import annotations

import asyncio
from asyncio.locks import Lock
from typing import TYPE_CHECKING

from geopandas import GeoDataFrame, read_file  # pyright: ignore[reportUnknownVariableType]
from pyproj import Transformer

from psagen.core.cache import async_cache
from psagen.core.logger import get_logger
from psagen.core.settings import settings
from psagen.models.enrich import Map

from .generator import generate_geo_calibrated_svg

if TYPE_CHECKING:
    from collections.abc import Callable

    from psagen.core.client import APIClient

logger = get_logger(__name__)

_NE_GEOJSON = "ne_50m_admin_0_countries.geojson"

_NE_FETCH_LOCK = Lock()
_ne_data: GeoDataFrame | None = None


@async_cache
async def fetch_map(client: APIClient, lat: float, lon: float, country_code: str) -> Map:
    """Get country map SVG and dot position."""
    # Only one of the tasks needs to fetch the NE dataset,
    # the rest should wait for it, and then they can simply use the local file.
    async with _NE_FETCH_LOCK:
        world = await _load_natural_earth_data(client)

    svg_data, bounds = await asyncio.to_thread(generate_geo_calibrated_svg, world, country_code)

    dot_pos = _dot_position(lat, lon, bounds)

    return Map(svg_content=svg_data, dot_position=dot_pos)


async def _load_natural_earth_data(client: APIClient) -> GeoDataFrame:
    """Load Natural Earth GeoJSON data from cache or download it."""
    global _ne_data  # noqa: PLW0603
    if _ne_data is not None:
        return _ne_data

    geojson_file = settings.cache_dir / _NE_GEOJSON

    if geojson_file.exists():
        try:
            _ne_data = await asyncio.to_thread(read_file, geojson_file)  # pyright: ignore[reportUnknownArgumentType]
        except Exception as e:  # noqa: BLE001
            logger.warning("Cached map data corrupt, re-downloading: %s", e)
        else:
            return _ne_data

    logger.info("Downloading Natural Earth 50m data...")

    content = await client.get(settings.natural_earth_geojson_url + _NE_GEOJSON)
    await asyncio.to_thread(geojson_file.write_bytes, content)

    _ne_data = await asyncio.to_thread(read_file, geojson_file)  # pyright: ignore[reportUnknownArgumentType]
    return _ne_data


_transform: Callable[[float, float], tuple[float, float]] = Transformer.from_crs(
    "EPSG:4326", "EPSG:3857", always_xy=True
).transform


def _dot_position(
    lat: float, lon: float, bounds: tuple[float, float, float, float]
) -> tuple[float, float]:
    """Calculate the relative position (0-100%) of a location dot within a country map."""
    min_x, min_y, max_x, max_y = bounds

    x, y = _transform(lon, lat)

    x_ratio = (x - min_x) / (max_x - min_x)
    y_ratio = (max_y - y) / (max_y - min_y)

    x_percent = 100 * max(0.0, min(x_ratio, 1))
    y_percent = 100 * max(0.0, min(y_ratio, 1))

    return x_percent, y_percent
