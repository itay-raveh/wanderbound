"""Main map service entry point."""

import asyncio
from collections.abc import Callable

from src.core.cache import get_cached, set_cached
from src.core.logger import get_logger
from src.data.models import MapResult, Step
from src.services.client import APIClient

from .coordinates import get_country_map_dot_position
from .generator import generate_geo_calibrated_svg

logger = get_logger(__name__)


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
        dot_position = get_country_map_dot_position(lon, lat, svg_data)

    return MapResult(
        step_index=step_index,
        svg_content=svg_data,
        dot_position=dot_position,
    )


async def fetch_maps_batch(
    client: APIClient, steps: list[Step], progress_callback: Callable[[int], None] | None = None
) -> list[MapResult]:
    """Fetch maps and calculate dot positions for all steps."""
    logger.debug("Fetching maps...")

    tasks = []
    for index, step in enumerate(steps):
        if not step.country_code:
            if progress_callback:
                progress_callback(1)
            tasks.append(asyncio.create_task(asyncio.sleep(0, result=MapResult(step_index=index))))
            continue

        tasks.append(
            asyncio.create_task(
                get_map_data(
                    client,
                    step.country_code,
                    index,
                    step.location.lat,
                    step.location.lon,
                )
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    if progress_callback:
        progress_callback(len(steps))

    map_results: list[MapResult] = []
    for i, res in enumerate(results):
        if isinstance(res, MapResult):
            map_results.append(res)
        else:
            logger.warning("Failed to fetch map for step %d: %s", i, res)
            map_results.append(MapResult(step_index=i))

    logger.debug("Processed %d maps", len(map_results))
    return map_results
