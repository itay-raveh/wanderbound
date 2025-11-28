"""Batch fetching of external data for HTML generation using async/await."""

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from src.core.logger import create_progress, get_console, get_logger
from src.core.settings import settings
from src.data.models import Photo, Step
from src.services.altitude import get_altitude_batch
from src.services.flags import (
    extract_prominent_color_from_flag,
    get_country_flag_data_uri_async,
)
from src.services.maps import (
    get_country_map_data_uri_async,
    get_country_map_dot_position,
    get_country_map_svg_async,
)
from src.services.utils import create_async_client
from src.services.weather import WeatherData, get_weather_data_async

from .assets import copy_image_to_assets
from .preparation import _clean_description

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
    with console.status("[bold blue]Fetching altitudes..."):
        logger.debug("Fetching altitudes...")
        locations = [(step.location.lat, step.location.lon) for step in steps]
        elevations = get_altitude_batch(locations)
    logger.debug("Fetched %d altitude values", len(elevations))
    return elevations


async def _fetch_weather_single(
    client: httpx.AsyncClient, step: Step, index: int
) -> tuple[int, WeatherData | None]:
    try:
        weather_data = await get_weather_data_async(
            client,
            step.location.lat,
            step.location.lon,
            step.start_time,
            step.timezone_id,
        )
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError, KeyError, TypeError) as e:
        logger.warning("Failed to fetch weather data for step %d: %s", index, e)
        return (index, None)
    else:
        return (index, weather_data)


def fetch_weather_data_batch(steps: list[Step]) -> list[WeatherData | None]:
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
                    logger.warning("Error in weather fetch task: %s", result)
                    weather_progress.advance(task_id)
                elif isinstance(result, tuple) and len(result) == 2:
                    idx, weather_data = result
                    weather_data_list[idx] = weather_data
                    weather_progress.advance(task_id)
                else:
                    logger.warning("Unexpected result type: %s", type(result))
                    weather_progress.advance(task_id)
        finally:
            await client.aclose()

    with weather_progress:
        task_id = weather_progress.add_task("Fetching weather data", total=len(steps))
        asyncio.run(_fetch_all())

    logger.debug("Fetched %d weather data entries", len(weather_data_list))
    return weather_data_list


async def _fetch_flag_single(
    client: httpx.AsyncClient, step: Step, index: int, *, light_mode: bool
) -> tuple[int, tuple[str | None, str | None] | None]:
    try:
        country_flag_data_uri = (
            await get_country_flag_data_uri_async(client, step.country_code)
            if step.country_code
            else None
        )
        accent_color = extract_prominent_color_from_flag(
            country_flag_data_uri, step.country_code, light_mode=light_mode
        )
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError, AttributeError) as e:
        logger.warning("Failed to process flag for step %d: %s", index, e)
        return (index, None)
    else:
        return (index, (country_flag_data_uri, accent_color))


def fetch_flags_batch(
    steps: list[Step], *, light_mode: bool
) -> list[tuple[str | None, str | None] | None]:
    logger.debug("Fetching flags and extracting colors...")
    flag_progress = create_progress("Processing flags")
    flag_data_list: list[tuple[str | None, str | None] | None] = [None] * len(steps)

    async def _fetch_all() -> None:
        client = create_async_client()
        try:
            tasks = [
                _fetch_flag_single(client, step, idx, light_mode=light_mode)
                for idx, step in enumerate(steps)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("Error in flag fetch task: %s", result)
                    flag_progress.advance(task_id)
                elif isinstance(result, tuple) and len(result) == 2:
                    idx, flag_data = result
                    flag_data_list[idx] = flag_data
                    flag_progress.advance(task_id)
                else:
                    logger.warning("Unexpected result type: %s", type(result))
                    flag_progress.advance(task_id)
        finally:
            await client.aclose()

    with flag_progress:
        task_id = flag_progress.add_task("Processing flags", total=len(steps))
        asyncio.run(_fetch_all())

    logger.debug("Processed %d flags", len(flag_data_list))
    return flag_data_list


async def _fetch_map_single(
    client: httpx.AsyncClient, step: Step, index: int
) -> tuple[int, tuple[str | None, str | None, tuple[float, float] | None] | None]:
    try:
        if step.country_code:
            country_map_data_uri = await get_country_map_data_uri_async(
                client, step.country_code, step.location.lat, step.location.lon
            )
            country_map_svg = await get_country_map_svg_async(
                client, step.country_code, step.location.lat, step.location.lon
            )
            dot_pos = get_country_map_dot_position(
                step.country_code, step.location.lat, step.location.lon, svg_data=country_map_svg
            )
            result = (index, (country_map_data_uri, country_map_svg, dot_pos))
        else:
            result = (index, (None, None, None))
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError, KeyError) as e:
        logger.warning("Failed to process map for step %d: %s", index, e)
        return (index, None)
    else:
        return result


def fetch_maps_batch(
    steps: list[Step],
) -> list[tuple[str | None, str | None, tuple[float, float] | None] | None]:
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
                    logger.warning("Error in map fetch task: %s", result)
                    map_progress.advance(task_id)
                elif isinstance(result, tuple) and len(result) == 2:
                    idx, map_data = result
                    map_data_list[idx] = map_data
                    map_progress.advance(task_id)
                else:
                    logger.warning("Unexpected result type: %s", type(result))
                    map_progress.advance(task_id)
        finally:
            await client.aclose()

    with map_progress:
        task_id = map_progress.add_task("Processing maps", total=len(steps))
        asyncio.run(_fetch_all())

    logger.debug("Processed %d maps", len(map_data_list))
    return map_data_list


def process_cover_images_batch(
    steps: list[Step],
    steps_cover_photos: dict[int, Photo | None],
    output_dir: Path,
) -> list[str | None]:
    logger.debug("Copying cover images to assets...")
    image_progress = create_progress("Processing images")
    cover_image_path_list: list[str | None] = [None] * len(steps)

    def _process_cover_image(step: Step) -> str | None:
        cover_photo = steps_cover_photos.get(step.id) if step.id else None
        description = _clean_description(step.description or "")
        # Using module-level settings
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
                except (OSError, ValueError, AttributeError) as e:
                    logger.warning("Failed to process cover image for step %d: %s", idx, e)
                    image_progress.advance(task_id)
    logger.debug("Processed %d cover images", len(cover_image_path_list))
    return cover_image_path_list
