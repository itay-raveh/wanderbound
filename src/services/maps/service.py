"""Main map service entry point."""

from __future__ import annotations

from asyncio.locks import Lock
from typing import TYPE_CHECKING

import geopandas as gpd
from lxml import etree
from pyproj import Transformer

from src.core.cache import cache_in_file
from src.core.logger import get_logger
from src.core.settings import settings
from src.models.trip import Map

from .generator import _ETREE_XML_PARSER, generate_geo_calibrated_svg

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.services.client import APIClient

logger = get_logger(__name__)

_NE_GEOJSON = "ne_50m_admin_0_countries.geojson"

_NE_FETCH_LOCK = Lock()


@cache_in_file()
async def fetch_map(
    client: APIClient, lat: float, lon: float, country_code: str
) -> Map:
    """Get country map SVG and dot position."""
    # Only one of the tasks needs to fetch the NE dataset,
    # the rest should wait for it, and then they can simply use the local file.
    await _NE_FETCH_LOCK.acquire()
    world = await _load_natural_earth_data(client)
    _NE_FETCH_LOCK.release()

    svg_data = generate_geo_calibrated_svg(world, country_code)
    return Map(
        svg_content=svg_data,
        dot_position=_dot_position(lat, lon, svg_data),
    )


async def _load_natural_earth_data(client: APIClient) -> gpd.GeoDataFrame:
    """Load Natural Earth GeoJSON data from cache or download it."""
    geojson_file = settings.cache_dir / _NE_GEOJSON

    if geojson_file.exists():
        try:
            return gpd.read_file(
                geojson_file
            )  # pyright: ignore[reportUnknownMemberType]
        except Exception as e:  # noqa: BLE001
            logger.warning("Cached map data corrupt, re-downloading: %s", e)

    logger.info("Downloading Natural Earth 50m data...")

    content = await client.get_content(settings.natural_earth_geojson_url + _NE_GEOJSON)
    geojson_file.write_bytes(content, encoding="utf-8")

    return gpd.read_file(geojson_file)  # pyright: ignore[reportUnknownMemberType]


_transform: Callable[[float, float], tuple[float, float]] = Transformer.from_crs(
    "EPSG:4326", "EPSG:3857", always_xy=True
).transform


def _dot_position(lat: float, lon: float, svg_data: str) -> tuple[float, float]:
    """Calculate the relative position (0-100%) of a location dot within a country map."""
    root = etree.fromstring(svg_data, parser=_ETREE_XML_PARSER)

    min_x, min_y, max_x, max_y = [
        float(x) for x in str(root.attrib["data-bounds"]).split(",")
    ]

    x, y = _transform(lon, lat)

    x_ratio = (x - min_x) / (max_x - min_x)
    y_ratio = (max_y - y) / (max_y - min_y)

    x_percent = 100 * max(0.0, min(x_ratio, 1))
    y_percent = 100 * max(0.0, min(y_ratio, 1))

    return x_percent, y_percent
