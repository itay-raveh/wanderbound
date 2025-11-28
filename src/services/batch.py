"""Batch fetching of external data for services."""

from src.core.batch import process_batch
from src.core.logger import create_progress, get_logger
from src.data.models import FlagResult, MapResult, Step, WeatherResult
from src.services.altitude import get_altitudes
from src.services.flags import get_flag_data
from src.services.maps import get_map_data
from src.services.utils import APIClient
from src.services.weather import get_weather_data

logger = get_logger(__name__)


async def fetch_altitudes(steps: list[Step]) -> list[float | None]:
    """Fetch altitudes for all steps."""
    logger.debug("Fetching altitudes...")
    locations = [(step.location.lat, step.location.lon) for step in steps]

    # Altitudes are fetched in batches within the service, so we don't need process_batch here
    # unless we want to parallelize the batches themselves, but get_altitudes handles chunking.
    # However, get_altitudes is now async and uses APIClient.

    client = APIClient(base_url="")
    try:
        with create_progress("Fetching altitudes") as progress:
            task_id = progress.add_task("Fetching altitudes", total=1)
            elevations = await get_altitudes(client, locations)
            progress.advance(task_id)
    finally:
        await client.close()

    logger.debug("Fetched %d altitude values", len(elevations))
    return elevations


async def fetch_weather_data_batch(steps: list[Step]) -> list[WeatherResult]:
    """Fetch weather data for all steps."""
    logger.debug("Fetching weather data...")

    client = APIClient(base_url="")

    async def _process_step(step: Step, index: int) -> WeatherResult:
        return await get_weather_data(
            client,
            step.location.lat,
            step.location.lon,
            step.start_time,
            step.timezone_id,
            index,
        )

    try:
        with create_progress("Fetching weather data") as progress:
            task_id = progress.add_task("Fetching weather data", total=len(steps))

            results = await process_batch(
                steps,
                _process_step,
                concurrency=10,
                progress_callback=lambda _: progress.advance(task_id),
            )
    finally:
        await client.close()

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


async def fetch_flags_batch(steps: list[Step], *, light_mode: bool) -> list[FlagResult]:
    """Fetch flags and extract colors for all steps."""
    logger.debug("Fetching flags and extracting colors...")

    client = APIClient(base_url="")

    async def _process_step(step: Step, index: int) -> FlagResult:
        if not step.country_code:
            return FlagResult(step_index=index)
        return await get_flag_data(client, step.country_code, index, light_mode=light_mode)

    try:
        with create_progress("Processing flags") as progress:
            task_id = progress.add_task("Processing flags", total=len(steps))

            results = await process_batch(
                steps,
                _process_step,
                concurrency=10,
                progress_callback=lambda _: progress.advance(task_id),
            )
    finally:
        await client.close()

    flag_results: list[FlagResult] = []
    for i, res in enumerate(results):
        if isinstance(res, FlagResult):
            flag_results.append(res)
        else:
            logger.warning("Failed to fetch flag for step %d: %s", i, res)
            flag_results.append(FlagResult(step_index=i))

    logger.debug("Processed %d flags", len(flag_results))
    return flag_results


async def fetch_maps_batch(steps: list[Step]) -> list[MapResult]:
    """Fetch maps and calculate dot positions for all steps."""
    logger.debug("Fetching maps and calculating positions...")

    client = APIClient(base_url="")

    async def _process_step(step: Step, index: int) -> MapResult:
        if not step.country_code:
            return MapResult(step_index=index)
        return await get_map_data(
            client,
            step.country_code,
            index,
            step.location.lat,
            step.location.lon,
        )

    try:
        with create_progress("Processing maps") as progress:
            task_id = progress.add_task("Processing maps", total=len(steps))

            results = await process_batch(
                steps,
                _process_step,
                concurrency=10,
                progress_callback=lambda _: progress.advance(task_id),
            )
    finally:
        await client.close()

    map_results: list[MapResult] = []
    for i, res in enumerate(results):
        if isinstance(res, MapResult):
            map_results.append(res)
        else:
            logger.warning("Failed to fetch map for step %d: %s", i, res)
            map_results.append(MapResult(step_index=i))

    logger.debug("Processed %d maps", len(map_results))
    return map_results
