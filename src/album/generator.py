"""Generate HTML pages for the photo album using Jinja templates."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.core.logger import create_progress, get_logger
from src.data.context import StepTemplateContext
from src.data.locations import LocationEntry
from src.data.models import (
    AlbumGenerationConfig,
    AlbumPhoto,
    FlagData,
    MapData,
    Step,
    StepContext,
    StepExternalData,
)
from src.data.trip import WeatherData
from src.services.altitude import fetch_altitudes
from src.services.client import APIClient
from src.services.flags import fetch_flags
from src.services.maps.service import fetch_maps
from src.services.overview import calculate_trip_overview
from src.services.weather import fetch_weather_data

from .assets import make_photo_pages_data
from .preparation import prepare_step_data

logger = get_logger(__name__)


@dataclass(frozen=True)
class GeneratorContext:
    """Context data for the album generation process."""

    steps: list[Step]
    photo_data: AlbumPhoto
    config: AlbumGenerationConfig
    use_step_range: bool
    light_mode: bool


@dataclass(frozen=True)
class FetchedData:
    """External data fetched for all steps."""

    elevations: list[float | None]
    weather_data_list: list[WeatherData | None]
    flag_data_list: list[FlagData | None]
    map_data_list: list[MapData | None]


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

        async with APIClient() as client:
            results = await asyncio.gather(
                fetch_altitudes(client, context.steps, progress_callback=update_alt),
                fetch_weather_data(client, context.steps, progress_callback=update_weather),
                fetch_flags(
                    client,
                    context.steps,
                    light_mode=context.light_mode,
                    progress_callback=update_flags,
                ),
                fetch_maps(client, context.steps, progress_callback=update_maps),
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
) -> list[StepTemplateContext]:
    """Process steps and prepare data for rendering."""
    steps_template_ctx: list[StepTemplateContext] = []
    progress = create_progress()

    with progress:
        task_id = progress.add_task("Preparing steps", total=len(context.steps))
        for idx, (
            step,
            elevation,
            weather_data,
            flag_data,
            map_data,
        ) in enumerate(
            progress.track(
                zip(
                    context.steps,
                    fetched_data.elevations,
                    fetched_data.weather_data_list,
                    fetched_data.flag_data_list,
                    fetched_data.map_data_list,
                    strict=True,
                ),
                task_id=task_id,
            )
        ):
            logger.debug("Processing step %d/%d: %s", idx + 1, len(context.steps), step.name)
            progress.update(task_id, description=f"Preparing steps: {step.name}")

            photo_pages = context.photo_data.steps_photo_pages.get(step.id, [])
            photo_pages_data = make_photo_pages_data(photo_pages)

            hidden_photos = context.photo_data.steps_hidden_photos.get(step.id, [])

            cover_photo = context.photo_data.steps_cover_photos.get(step.id)

            external_data = StepExternalData(
                elevation=elevation,
                weather_data=weather_data,
                flag_data=flag_data,
                map_data=map_data,
                cover_photo=cover_photo,
            )

            step_context = StepContext(
                step=step,
                step_index=idx,
                steps=context.steps,
                trip=context.config.trip,
            )
            step_data = prepare_step_data(
                step_context,
                external_data,
                use_step_range=context.use_step_range,
                light_mode=context.light_mode,
            )
            step_data.photo_pages = photo_pages_data
            step_data.hidden_photos = hidden_photos
            steps_template_ctx.append(step_data)

        progress.update(task_id, description="Preparing steps")

    logger.debug("Step data prepared")
    return steps_template_ctx


async def generate_album_html(
    steps: list[Step],
    photo_data: AlbumPhoto,
    config: AlbumGenerationConfig,
    locations: list[LocationEntry],
    *,
    use_step_range: bool = False,
    light_mode: bool = False,
) -> Path:
    """Generate HTML pages for the photo album."""
    context = GeneratorContext(
        steps=steps,
        photo_data=photo_data,
        config=config,
        use_step_range=use_step_range,
        light_mode=light_mode,
    )

    # Batch fetch all external data
    fetched_data = await _fetch_external_data(context)

    # Prepare step data
    steps_template_ctx = _process_steps(context, fetched_data)

    # Calculate trip overview
    trip_overview = calculate_trip_overview(
        steps=steps,
        photo_data=photo_data,
        locations=locations,
    )

    # Render template
    template_dir = Path(__file__).parents[2] / "static"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("album.html.jinja")
    html = template.render(
        trip=config.trip_template_ctx,
        steps=steps_template_ctx,
        light_mode=light_mode,
        editor_mode=config.editor_mode,
        overview=trip_overview,
    )

    # Write output
    output_path = config.output_dir / "album.html"
    output_path.write_text(html, encoding="utf-8")

    return output_path
