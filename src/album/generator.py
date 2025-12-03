"""Generate HTML pages for the photo album using Jinja templates."""

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.core.logger import create_progress, get_logger
from src.core.settings import settings
from src.core.types import (
    AlbumGenerationConfig,
    AlbumPhotoData,
    StepContext,
    StepData,
    StepExternalData,
)
from src.data.models import FlagResult, MapResult, Step, TripData, WeatherResult
from src.services.batch import (
    fetch_altitudes,
    fetch_flags_batch,
    fetch_maps_batch,
    fetch_weather_data_batch,
)

from .assets import copy_cover_images, copy_photo_pages
from .preparation import prepare_step_data
from .renderer import create_template_environment, render_album_template

logger = get_logger(__name__)


@dataclass(frozen=True)
class GeneratorContext:
    """Context data for the album generation process."""

    steps: list[Step]
    photo_data: AlbumPhotoData
    config: AlbumGenerationConfig
    output_dir: Path
    trip_data: TripData
    use_step_range: bool
    light_mode: bool


def _copy_static_files(context: GeneratorContext) -> None:
    """Copy static files to output directory."""
    static_dir = Path(__file__).parent.parent.parent / "static"
    if static_dir.exists():
        for item in static_dir.iterdir():
            if item.name == "album.html.jinja":
                continue
            dest = context.output_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)


@dataclass(frozen=True)
class FetchedData:
    """External data fetched for all steps."""

    elevations: list[float | None]
    weather_data_list: list[WeatherResult]
    flag_data_list: list[FlagResult]
    map_data_list: list[MapResult]


async def _fetch_external_data(context: GeneratorContext) -> FetchedData:
    """Fetch all external data concurrently."""
    progress = create_progress()

    with progress:
        # Create tasks
        alt_task = progress.add_task("Fetching altitudes", total=len(context.steps))
        weather_task = progress.add_task("Fetching weather", total=len(context.steps))
        flag_task = progress.add_task("Fetching flags", total=len(context.steps))
        map_task = progress.add_task("Fetching maps", total=len(context.steps))

        # Define callbacks
        def update_alt(count: int) -> None:
            progress.update(alt_task, completed=count)

        def update_weather(count: int) -> None:
            progress.update(weather_task, completed=count)

        def update_flags(count: int) -> None:
            progress.update(flag_task, completed=count)

        def update_maps(count: int) -> None:
            progress.update(map_task, completed=count)

        results = await asyncio.gather(
            fetch_altitudes(context.steps, progress_callback=update_alt),
            fetch_weather_data_batch(context.steps, progress_callback=update_weather),
            fetch_flags_batch(
                context.steps,
                light_mode=context.light_mode,
                progress_callback=update_flags,
            ),
            fetch_maps_batch(context.steps, progress_callback=update_maps),
        )

    return FetchedData(
        elevations=results[0],
        weather_data_list=results[1],
        flag_data_list=results[2],
        map_data_list=results[3],
    )


def _process_steps(
    context: GeneratorContext,
    fetched_data: FetchedData,
    cover_image_path_list: list[str | None],
) -> list[StepData]:
    """Process steps and prepare data for rendering."""
    logger.debug("Preparing step data...")
    step_data_list: list[StepData] = []
    steps_photo_pages = context.photo_data["steps_photo_pages"]
    steps_cover_photos = context.photo_data["steps_cover_photos"]

    progress = create_progress()

    with progress:
        task_id = progress.add_task("Preparing steps", total=len(context.steps))
        for idx, (
            step,
            elevation,
            weather_result,
            flag_result,
            map_result,
            cover_image_path,
        ) in enumerate(
            progress.track(
                zip(
                    context.steps,
                    fetched_data.elevations,
                    fetched_data.weather_data_list,
                    fetched_data.flag_data_list,
                    fetched_data.map_data_list,
                    cover_image_path_list,
                    strict=True,
                ),
                task_id=task_id,
            )
        ):
            logger.debug("Processing step %d/%d: %s", idx + 1, len(context.steps), step.city)
            progress.update(task_id, description=f"Preparing steps: {step.city}")

            if weather_result.data is None:
                logger.debug("Missing weather data for step %d (%s)", idx, step.city)

            # Ensure cover photo access (side effect check from original code)
            steps_cover_photos.get(step.id) if step.id else None

            photo_pages = steps_photo_pages.get(step.id, []) if step.id else []

            # Copy photo pages images to assets directory
            step_name = step.get_name_for_photos_export()
            photo_pages_paths = copy_photo_pages(
                photo_pages,
                step_name,
                context.output_dir,
            )

            external_data: StepExternalData = {
                "elevation": elevation,
                "weather_data": weather_result,
                "flag_data": flag_result,
                "map_data": map_result,
                "cover_image_path": cover_image_path,
            }

            step_context: StepContext = {
                "step": step,
                "step_index": idx,
                "steps": context.steps,
                "trip_data": context.trip_data,
            }
            step_data = prepare_step_data(
                step_context,
                external_data,
                use_step_range=context.use_step_range,
                light_mode=context.light_mode,
            )
            step_data["photo_pages"] = photo_pages_paths
            step_data_list.append(step_data)

        progress.update(task_id, description="Preparing steps")

    logger.debug("Step data prepared")
    return step_data_list


def generate_album_html(
    steps: list[Step],
    photo_data: AlbumPhotoData,
    config: AlbumGenerationConfig,
    *,
    use_step_range: bool = False,
    light_mode: bool = False,
) -> Path:
    """Generate HTML pages for the photo album."""
    context = GeneratorContext(
        steps=steps,
        photo_data=photo_data,
        config=config,
        output_dir=Path(config["output_dir"]),
        trip_data=config["trip_data"],
        use_step_range=use_step_range,
        light_mode=light_mode,
    )

    _copy_static_files(context)

    # Batch fetch all external data
    fetched_data = asyncio.run(_fetch_external_data(context))

    # Process cover images
    cover_image_path_list = copy_cover_images(
        context.steps, context.photo_data["steps_cover_photos"], context.output_dir
    )

    # Prepare step data
    step_data_list = _process_steps(
        context,
        fetched_data,
        cover_image_path_list,
    )

    # Render template
    env = create_template_environment()
    template = env.get_template("album.html.jinja")
    html = render_album_template(template, step_data_list, light_mode=context.light_mode)

    # Write output
    output_path = context.output_dir / settings.file.album_html_file
    output_path.write_text(html, encoding="utf-8")

    return output_path
