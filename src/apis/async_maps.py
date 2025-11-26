"""Async country map API integration using httpx."""

import httpx

from ..logger import get_logger
from .cache import get_cached

logger = get_logger(__name__)


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

    # Generate geo-calibrated SVG
    try:
        from .cache import set_cached
        from .maps import _generate_geo_calibrated_svg

        svg_data = _generate_geo_calibrated_svg(country_code)
        if svg_data:
            set_cached(cache_key_svg, svg_data)
            return svg_data
    except Exception as e:
        logger.warning(f"Failed to generate geo-calibrated SVG for {country_code}: {e}")

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
