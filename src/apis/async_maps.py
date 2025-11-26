"""Async country map API integration using httpx."""

import httpx

from ..logger import get_logger
from ..settings import get_settings
from .async_helpers import fetch_and_cache_text_async
from .cache import get_cached
from .maps import (
    _parse_svg_with_lxml,
)

logger = get_logger(__name__)

# Maps API rate limit: Conservative rate for GitHub raw URLs
MAPS_API_CALLS_PER_SECOND = 2


async def get_country_map_svg_async(
    client: httpx.AsyncClient,
    country_code: str,
    lat: float | None = None,
    lon: float | None = None,
) -> str | None:
    """Get country map/silhouette as raw SVG string (async).

    Args:
        client: httpx AsyncClient instance
        country_code: ISO country code (e.g., "us", "fr")
        lat: Optional latitude (for geo-calibrated SVG)
        lon: Optional longitude (for geo-calibrated SVG)

    Returns:
        SVG string, or None if fetch/processing fails
    """
    if not country_code:
        return None

    cache_key_svg = f"map_svg_{country_code.lower()}"
    cached_svg = get_cached(cache_key_svg)
    if cached_svg is not None and isinstance(cached_svg, str):
        return str(cached_svg)

    # Try geo-calibrated SVG first (if geopandas is available)
    try:
        from .cache import set_cached
        from .maps import HAS_GEO, _generate_geo_calibrated_svg

        if HAS_GEO:
            svg_data = _generate_geo_calibrated_svg(country_code)
            if svg_data:
                set_cached(cache_key_svg, svg_data)
                return svg_data
    except Exception as e:
        logger.debug(f"Geo-calibrated SVG generation failed: {e}")

    # Fallback to fetching from mapsicon URL
    settings = get_settings()
    svg_url = settings.mapsicon_url.format(country_code=country_code.lower())

    try:
        svg_data = await fetch_and_cache_text_async(
            client, cache_key_svg, svg_url, timeout=10.0, max_attempts=3
        )

        if not svg_data:
            return None

        # Parse SVG with lxml
        root = _parse_svg_with_lxml(svg_data)
        if root is None:
            return None

        # Convert back to string
        from lxml import etree

        svg_string = etree.tostring(root, encoding="unicode", pretty_print=False)
        from .cache import set_cached

        set_cached(cache_key_svg, svg_string)
        return svg_string
    except Exception as e:
        logger.warning(f"Failed to get map SVG for {country_code}: {e}")

    return None


async def get_country_map_data_uri_async(
    client: httpx.AsyncClient,
    country_code: str,
    lat: float | None = None,
    lon: float | None = None,
) -> str | None:
    """Get country map/silhouette image as data URI (async).

    Args:
        client: httpx AsyncClient instance
        country_code: ISO country code (e.g., "us", "fr")
        lat: Optional latitude
        lon: Optional longitude

    Returns:
        Data URI string for the map image, or None if fetch fails
    """
    # Use the synchronous version which handles caching internally
    # The SVG fetching is async, but the data URI conversion is simple
    svg_data = await get_country_map_svg_async(client, country_code, lat, lon)
    if svg_data:
        import base64

        from .cache import get_cached, set_cached

        cache_key = f"map_{country_code.lower()}"
        cached = get_cached(cache_key)
        if cached is not None and isinstance(cached, str):
            return str(cached)

        svg_encoded = base64.b64encode(svg_data.encode("utf-8")).decode("utf-8")
        data_uri = f"data:image/svg+xml;base64,{svg_encoded}"
        set_cached(cache_key, data_uri)
        return data_uri

    return None
