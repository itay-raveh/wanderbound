"""Batch fetching of external data for HTML generation."""

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

from ..apis import (
    extract_prominent_color_from_flag,
    get_altitude_batch,
    get_country_flag_data_uri,
    get_country_map_data_uri,
    get_country_map_dot_position,
    get_country_map_svg,
)
from ..apis.weather import WeatherData, get_weather_data
from ..html.asset_management import copy_image_to_assets
from ..html.step_data_preparation import _clean_description
from ..logger import create_progress, get_console, get_logger
from ..models import Photo, Step
from ..settings import get_settings

logger = get_logger(__name__)
console = get_console()

__all__ = [
    "fetch_altitudes",
    "fetch_weather_data_batch",
    "fetch_flags_batch",
    "fetch_maps_batch",
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


def fetch_weather_data_batch(steps: list[Step]) -> list[WeatherData | None]:
    """Fetch weather data for all steps in parallel.

    Args:
        steps: List of steps to fetch weather data for

    Returns:
        List of WeatherData objects or None for each step
    """
    logger.debug("Fetching weather data...")
    weather_progress = create_progress("Fetching weather data")
    weather_data_list: list[WeatherData | None] = [None] * len(steps)
    with weather_progress:
        task_id = weather_progress.add_task("Fetching weather data", total=len(steps))
        with ThreadPoolExecutor(max_workers=5) as weather_executor:
            weather_future_to_index: dict[Future[WeatherData | None], int] = {
                weather_executor.submit(
                    get_weather_data,
                    step.location.lat,
                    step.location.lon,
                    step.start_time,
                    step.timezone_id,
                ): idx
                for idx, step in enumerate(steps)
            }
            for future in as_completed(weather_future_to_index):
                idx = weather_future_to_index[future]
                try:
                    result = future.result()
                    weather_data_list[idx] = result
                    weather_progress.advance(task_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch weather data for step {idx}: {e}")
                    weather_progress.advance(task_id)
    logger.debug(f"Fetched {len(weather_data_list)} weather data entries")
    return weather_data_list


def fetch_flags_batch(
    steps: list[Step], light_mode: bool
) -> list[tuple[str | None, str | None] | None]:
    """Fetch flags and extract accent colors for all steps in parallel.

    Args:
        steps: List of steps to fetch flags for
        light_mode: If True, use light mode color scheme

    Returns:
        List of tuples (country_flag_data_uri, accent_color) or None for each step
    """
    logger.debug("Fetching flags and extracting colors...")
    flag_progress = create_progress("Processing flags")
    flag_data_list: list[tuple[str | None, str | None] | None] = [None] * len(steps)
    with flag_progress:
        task_id = flag_progress.add_task("Processing flags", total=len(steps))

        def _process_flag(step: Step) -> tuple[str | None, str | None]:
            country_flag_data_uri = (
                get_country_flag_data_uri(step.country_code) if step.country_code else None
            )
            accent_color = extract_prominent_color_from_flag(
                country_flag_data_uri, step.country_code, light_mode
            )
            return (country_flag_data_uri, accent_color)

        with ThreadPoolExecutor(max_workers=5) as flag_executor:
            flag_future_to_index: dict[Future[tuple[str | None, str | None] | None], int] = {
                flag_executor.submit(_process_flag, step): idx for idx, step in enumerate(steps)
            }
            for future in as_completed(flag_future_to_index):
                idx = flag_future_to_index[future]
                try:
                    result = future.result()
                    flag_data_list[idx] = result
                    flag_progress.advance(task_id)
                except Exception as e:
                    logger.warning(f"Failed to process flag for step {idx}: {e}")
                    flag_progress.advance(task_id)
    logger.debug(f"Processed {len(flag_data_list)} flags")
    return flag_data_list


def fetch_maps_batch(
    steps: list[Step],
) -> list[tuple[str | None, str | None, tuple[float, float] | None] | None]:
    """Fetch maps and calculate dot positions for all steps in parallel.

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

    def _process_map(step: Step) -> tuple[str | None, str | None, tuple[float, float] | None]:
        if step.country_code:
            country_map_data_uri = get_country_map_data_uri(
                step.country_code, step.location.lat, step.location.lon
            )
            country_map_svg = get_country_map_svg(
                step.country_code, step.location.lat, step.location.lon
            )
            dot_pos = get_country_map_dot_position(
                step.country_code, step.location.lat, step.location.lon
            )
            return (country_map_data_uri, country_map_svg, dot_pos)
        return (None, None, None)

    with map_progress:
        task_id = map_progress.add_task("Processing maps", total=len(steps))
        with ThreadPoolExecutor(max_workers=5) as map_executor:
            map_future_to_index: dict[
                Future[tuple[str | None, str | None, tuple[float, float] | None]], int
            ] = {map_executor.submit(_process_map, step): idx for idx, step in enumerate(steps)}
            for future in as_completed(map_future_to_index):
                idx = map_future_to_index[future]
                try:
                    result = future.result()
                    map_data_list[idx] = result
                    map_progress.advance(task_id)
                except Exception as e:
                    logger.warning(f"Failed to process map for step {idx}: {e}")
                    map_progress.advance(task_id)
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
