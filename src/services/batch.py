"""Batch fetching of external data for services."""

from collections.abc import Callable

from src.core.batch import BatchConfig, BatchProcessor
from src.core.logger import get_logger
from src.data.models import FlagResult, MapResult, Step, WeatherResult
from src.services.altitude import get_altitudes
from src.services.client import APIClient
from src.services.flags import get_flag_data
from src.services.maps import get_map_data
from src.services.weather import get_weather_data

logger = get_logger(__name__)


async def fetch_altitudes(
    steps: list[Step], progress_callback: Callable[[int], None] | None = None
) -> list[float | None]:
    """Fetch altitudes for all steps."""
    logger.debug("Fetching altitudes...")
    locations = [(step.location.lat, step.location.lon) for step in steps]

    async with APIClient() as client:
        # get_altitudes handles its own batching/chunking logic for the API
        # We just wrap it to provide progress feedback if needed
        elevations = await get_altitudes(client, locations)

        if progress_callback:
            progress_callback(len(steps))

    logger.debug("Fetched %d altitude values", len(elevations))
    return elevations


async def fetch_weather_data_batch(
    steps: list[Step], progress_callback: Callable[[int], None] | None = None
) -> list[WeatherResult]:
    """Fetch weather data for all steps."""
    logger.debug("Fetching weather data...")

    async with APIClient() as client:
        # To handle indices, we'll pass tuples of (index, step) to the processor
        items = list(enumerate(steps))

        async def _process_item(item: tuple[int, Step]) -> WeatherResult:
            index, step = item
            return await get_weather_data(
                client,
                step.location.lat,
                step.location.lon,
                step.start_time,
                step.timezone_id,
                index,
            )

        tuple_processor = BatchProcessor[tuple[int, Step], WeatherResult](
            BatchConfig(concurrency=10)
        )

        results = await tuple_processor.process_batch(
            items,
            _process_item,
            progress_callback=progress_callback,
        )

    # Filter out exceptions and ensure type safety
    weather_results: list[WeatherResult] = []
    for i, res in enumerate(results):
        if isinstance(res, WeatherResult):
            weather_results.append(res)
        else:
            logger.warning("Failed to fetch weather for step %d: %s", i, res)
            weather_results.append(WeatherResult(step_index=i, data=None))

    logger.debug("Fetched %d weather data entries", len(weather_results))
    return weather_results


async def fetch_flags_batch(
    steps: list[Step],
    *,
    light_mode: bool,
    progress_callback: Callable[[int], None] | None = None,
) -> list[FlagResult]:
    """Fetch flags and extract colors for all steps."""
    logger.debug("Fetching flags and extracting colors...")

    async with APIClient() as client:
        items = list(enumerate(steps))

        async def _process_item(item: tuple[int, Step]) -> FlagResult:
            index, step = item
            if not step.country_code:
                return FlagResult(step_index=index)
            return await get_flag_data(client, step.country_code, index, light_mode=light_mode)

        processor = BatchProcessor[tuple[int, Step], FlagResult](BatchConfig(concurrency=10))

        results = await processor.process_batch(
            items,
            _process_item,
            progress_callback=progress_callback,
        )

    flag_results: list[FlagResult] = []
    for i, res in enumerate(results):
        if isinstance(res, FlagResult):
            flag_results.append(res)
        else:
            logger.warning("Failed to fetch flag for step %d: %s", i, res)
            flag_results.append(FlagResult(step_index=i))

    logger.debug("Processed %d flags", len(flag_results))
    return flag_results


async def fetch_maps_batch(
    steps: list[Step], progress_callback: Callable[[int], None] | None = None
) -> list[MapResult]:
    """Fetch maps and calculate dot positions for all steps."""
    logger.debug("Fetching maps and calculating positions...")

    async with APIClient() as client:
        items = list(enumerate(steps))

        async def _process_item(item: tuple[int, Step]) -> MapResult:
            index, step = item
            if not step.country_code:
                return MapResult(step_index=index)
            return await get_map_data(
                client,
                step.country_code,
                index,
                step.location.lat,
                step.location.lon,
            )

        processor = BatchProcessor[tuple[int, Step], MapResult](BatchConfig(concurrency=10))

        results = await processor.process_batch(
            items,
            _process_item,
            progress_callback=progress_callback,
        )

    map_results: list[MapResult] = []
    for i, res in enumerate(results):
        if isinstance(res, MapResult):
            map_results.append(res)
        else:
            logger.warning("Failed to fetch map for step %d: %s", i, res)
            map_results.append(MapResult(step_index=i))

    logger.debug("Processed %d maps", len(map_results))
    return map_results
