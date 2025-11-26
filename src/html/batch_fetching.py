"""Batch fetching of external data for HTML generation using async/await."""

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from ..apis import (
    extract_prominent_color_from_flag,
    get_altitude_batch,
    get_country_map_dot_position,
)
from ..apis.flags import get_country_flag_data_uri_async
from ..apis.helpers import create_async_client
from ..apis.maps import get_country_map_data_uri_async, get_country_map_svg_async
from ..apis.weather import WeatherData, get_weather_data_async
from ..html.asset_management import copy_image_to_assets
from ..html.step_data_preparation import _clean_description
from ..logger import create_progress, get_console, get_logger
from ..models import Photo, Step
from ..settings import get_settings

logger = get_logger(__name__)
console = get_console()

__all__ = [
    "fetch_altitudes",
    "fetch_flags_batch",
    "fetch_maps_batch",
    "fetch_weather_data_batch",
    "process_cover_images_batch",
]


def fetch_altitudes(steps: list[Step]) -> list[float | None]:
    """Fetch altitudes for all steps in batch.

    Args:
        steps: List of steps to fetch altitudes for

    Returns:
        List of altitude values (in meters) or None for each step
    """
    with console.status("[bold blue]Fetching altitudes..."):
        logger.debug("Fetching altitudes...")
        locations = [(step.location.lat, step.location.lon) for step in steps]
        elevations = get_altitude_batch(locations)
    logger.debug(f"Fetched {len(elevations)} altitude values")
    return elevations


async def _fetch_weather_single(
    client: httpx.AsyncClient, step: Step, index: int
) -> tuple[int, WeatherData | None]:
    """Fetch weather data for a single step (async helper).

    Args:
        client: httpx AsyncClient instance
        step: Step to fetch weather data for
        index: Step index for ordering

    Returns:
        Tuple of (index, WeatherData or None)
    """
    try:
        weather_data = await get_weather_data_async(
            client,
            step.location.lat,
            step.location.lon,
            step.start_time,
            step.timezone_id,
        )
        return (index, weather_data)
    except Exception as e:
        logger.warning(f"Failed to fetch weather data for step {index}: {e}")
        return (index, None)


def fetch_weather_data_batch(steps: list[Step]) -> list[WeatherData | None]:
    """Fetch weather data for all steps in parallel using async/await.

    Args:
        steps: List of steps to fetch weather data for

    Returns:
        List of WeatherData objects or None for each step
    """
    logger.debug("Fetching weather data...")
    weather_progress = create_progress("Fetching weather data")
    weather_data_list: list[WeatherData | None] = [None] * len(steps)

    async def _fetch_all() -> None:
        client = create_async_client()
        try:
            tasks = [_fetch_weather_single(client, step, idx) for idx, step in enumerate(steps)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Error in weather fetch task: {result}")
                    weather_progress.advance(task_id)
                elif isinstance(result, tuple) and len(result) == 2:
                    idx, weather_data = result
                    weather_data_list[idx] = weather_data
                    weather_progress.advance(task_id)
                else:
                    logger.warning(f"Unexpected result type: {type(result)}")
                    weather_progress.advance(task_id)
        finally:
            await client.aclose()

    with weather_progress:
        task_id = weather_progress.add_task("Fetching weather data", total=len(steps))
        asyncio.run(_fetch_all())

    logger.debug(f"Fetched {len(weather_data_list)} weather data entries")
    return weather_data_list


async def _fetch_flag_single(
    client: httpx.AsyncClient, step: Step, index: int, light_mode: bool
) -> tuple[int, tuple[str | None, str | None] | None]:
    """Fetch flag and extract accent color for a single step (async helper).

    Args:
        client: httpx AsyncClient instance
        step: Step to fetch flag for
        index: Step index for ordering
        light_mode: If True, use light mode color scheme

    Returns:
        Tuple of (index, (country_flag_data_uri, accent_color) or None)
    """
    try:
        country_flag_data_uri = (
            await get_country_flag_data_uri_async(client, step.country_code)
            if step.country_code
            else None
        )
        accent_color = extract_prominent_color_from_flag(
            country_flag_data_uri, step.country_code, light_mode
        )
        return (index, (country_flag_data_uri, accent_color))
    except Exception as e:
        logger.warning(f"Failed to process flag for step {index}: {e}")
        return (index, None)


def fetch_flags_batch(
    steps: list[Step], light_mode: bool
) -> list[tuple[str | None, str | None] | None]:
    """Fetch flags and extract accent colors for all steps in parallel using async/await.

    Args:
        steps: List of steps to fetch flags for
        light_mode: If True, use light mode color scheme

    Returns:
        List of tuples (country_flag_data_uri, accent_color) or None for each step
    """
    logger.debug("Fetching flags and extracting colors...")
    flag_progress = create_progress("Processing flags")
    flag_data_list: list[tuple[str | None, str | None] | None] = [None] * len(steps)

    async def _fetch_all() -> None:
        client = create_async_client()
        try:
            tasks = [
                _fetch_flag_single(client, step, idx, light_mode) for idx, step in enumerate(steps)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Error in flag fetch task: {result}")
                    flag_progress.advance(task_id)
                elif isinstance(result, tuple) and len(result) == 2:
                    idx, flag_data = result
                    flag_data_list[idx] = flag_data
                    flag_progress.advance(task_id)
                else:
                    logger.warning(f"Unexpected result type: {type(result)}")
                    flag_progress.advance(task_id)
        finally:
            await client.aclose()

    with flag_progress:
        task_id = flag_progress.add_task("Processing flags", total=len(steps))
        asyncio.run(_fetch_all())

    logger.debug(f"Processed {len(flag_data_list)} flags")
    return flag_data_list


async def _fetch_map_single(
    client: httpx.AsyncClient, step: Step, index: int
) -> tuple[int, tuple[str | None, str | None, tuple[float, float] | None] | None]:
    """Fetch map and calculate dot position for a single step (async helper).

    Args:
        client: httpx AsyncClient instance
        step: Step to fetch map for
        index: Step index for ordering

    Returns:
        Tuple of (index, (country_map_data_uri, country_map_svg, (map_dot_x, map_dot_y)) or None)
    """
    try:
        if step.country_code:
            country_map_data_uri = await get_country_map_data_uri_async(
                client, step.country_code, step.location.lat, step.location.lon
            )
            country_map_svg = await get_country_map_svg_async(
                client, step.country_code, step.location.lat, step.location.lon
            )
            dot_pos = get_country_map_dot_position(
                step.country_code, step.location.lat, step.location.lon
            )
            return (index, (country_map_data_uri, country_map_svg, dot_pos))
        return (index, (None, None, None))
    except Exception as e:
        logger.warning(f"Failed to process map for step {index}: {e}")
        return (index, None)


def fetch_maps_batch(
    steps: list[Step],
) -> list[tuple[str | None, str | None, tuple[float, float] | None] | None]:
    """Fetch maps and calculate dot positions for all steps in parallel using async/await.

    Args:
        steps: List of steps to fetch maps for

    Returns:
        List of tuples (country_map_data_uri, country_map_svg, (map_dot_x, map_dot_y)) or None for each step
    """
    logger.debug("Fetching maps and calculating positions...")
    map_progress = create_progress("Processing maps")
    map_data_list: list[tuple[str | None, str | None, tuple[float, float] | None] | None] = [
        None
    ] * len(steps)

    async def _fetch_all() -> None:
        client = create_async_client()
        try:
            tasks = [_fetch_map_single(client, step, idx) for idx, step in enumerate(steps)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"Error in map fetch task: {result}")
                    map_progress.advance(task_id)
                elif isinstance(result, tuple) and len(result) == 2:
                    idx, map_data = result
                    map_data_list[idx] = map_data
                    map_progress.advance(task_id)
                else:
                    logger.warning(f"Unexpected result type: {type(result)}")
                    map_progress.advance(task_id)
        finally:
            await client.aclose()

    with map_progress:
        task_id = map_progress.add_task("Processing maps", total=len(steps))
        asyncio.run(_fetch_all())

    logger.debug(f"Processed {len(map_data_list)} maps")
    return map_data_list


def process_cover_images_batch(
    steps: list[Step],
    steps_cover_photos: dict[int, Photo | None],
    output_dir: Path,
) -> list[str | None]:
    """Process and copy cover images for all steps in parallel.

    Args:
        steps: List of steps to process cover images for
        steps_cover_photos: Dictionary mapping step IDs to cover Photo objects
        output_dir: Output directory (parent of assets/)

    Returns:
        List of relative paths to cover images or None for each step
    """
    logger.debug("Copying cover images to assets...")
    image_progress = create_progress("Processing images")
    cover_image_path_list: list[str | None] = [None] * len(steps)

    def _process_cover_image(step: Step) -> str | None:
        cover_photo = steps_cover_photos.get(step.id) if step.id else None
        description = _clean_description(step.description or "")
        settings = get_settings()
        use_three_columns = len(description) > settings.description_three_columns_threshold
        use_two_columns = (
            len(description) > settings.description_two_columns_threshold or use_three_columns
        )
        if cover_photo and cover_photo.path.exists() and not use_two_columns:
            step_name = step.get_name_for_photos_export()
            return copy_image_to_assets(
                cover_photo.path,
                output_dir,
                step_name,
                cover_photo.index,
            )
        return None

    with image_progress:
        task_id = image_progress.add_task("Processing images", total=len(steps))
        with ThreadPoolExecutor(max_workers=5) as image_executor:
            image_future_to_index: dict[Future[str | None], int] = {
                image_executor.submit(_process_cover_image, step): idx
                for idx, step in enumerate(steps)
            }
            for future in as_completed(image_future_to_index):
                idx = image_future_to_index[future]
                try:
                    result = future.result()
                    cover_image_path_list[idx] = result
                    image_progress.advance(task_id)
                except Exception as e:
                    logger.warning(f"Failed to process cover image for step {idx}: {e}")
                    image_progress.advance(task_id)
    logger.debug(f"Processed {len(cover_image_path_list)} cover images")
    return cover_image_path_list
