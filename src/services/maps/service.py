"""Main map service entry point."""

from src.core.cache import get_cached, set_cached
from src.data.models import MapResult
from src.services.client import APIClient

from .coordinates import get_country_map_dot_position
from .generator import generate_geo_calibrated_svg


async def get_map_data(
    client: APIClient,
    country_code: str,
    step_index: int,
    lat: float | None = None,
    lon: float | None = None,
) -> MapResult:
    """Get country map SVG and dot position.

    Raises:
        ValueError: If country code is missing or invalid.
        RuntimeError: If map generation fails.
    """
    if not country_code:
        # This is a valid case where we just don't have a map
        return MapResult(step_index=step_index)

    cache_key_svg = f"map_svg_{country_code.lower()}"
    cached_svg = await get_cached(cache_key_svg)

    svg_data: str
    if cached_svg is not None and isinstance(cached_svg, str):
        svg_data = str(cached_svg)
    else:
        svg_data = await generate_geo_calibrated_svg(client, country_code)
        await set_cached(cache_key_svg, svg_data)

    dot_position = None
    if lat is not None and lon is not None:
        dot_position = get_country_map_dot_position(lat, lon, svg_data)

    return MapResult(
        step_index=step_index,
        svg_content=svg_data,
        dot_position=dot_position,
    )
