"""Generate HTML pages for the photo album using Jinja templates."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.core.logger import get_logger
from src.core.settings import settings
from src.data.context import StepTemplateContext
from src.data.locations import LocationEntry
from src.data.models import (
    AlbumGenerationConfig,
    AlbumPhoto,
    Step,
    StepContext,
)
from src.data.trip import EnrichedStep
from src.services.altitude import fetch_all_altitudes
from src.services.client import APIClient
from src.services.flags import fetch_flag
from src.services.maps.service import fetch_map
from src.services.overview import calculate_trip_overview
from src.services.weather import fetch_weather

from .assets import make_photo_pages_data
from .preparation import prepare_step_template

logger = get_logger(__name__)


@dataclass
class GeneratorContext:
    """Context data for the album generation process."""

    steps: list[Step]
    photo_data: AlbumPhoto
    config: AlbumGenerationConfig
    use_step_range: bool


async def _enrich_steps(steps: list[Step]) -> list[EnrichedStep]:
    """Fetch all external data concurrently."""
    async with APIClient() as client:
        results = await asyncio.gather(
            *(
                asyncio.gather(
                    fetch_weather(client, step),
                    fetch_flag(client, step.location.country_code),
                    fetch_map(client, step.location),
                )
                for step in steps
            ),
        )

        alts = await fetch_all_altitudes(client, steps)

    return [
        EnrichedStep(
            **step.model_dump(by_alias=True),  # pyright: ignore[reportAny]
            altitude=altitude,
            weather=weather,
            flag=flag,
            map=map_,
        )
        for step, altitude, (weather, flag, map_) in zip(steps, alts, results, strict=True)
    ]


def _process_steps(
    context: GeneratorContext, steps: list[EnrichedStep]
) -> list[StepTemplateContext]:
    """Process steps and prepare data for rendering."""
    steps_template_ctx: list[StepTemplateContext] = []

    for idx, step in enumerate(steps):
        photo_pages = context.photo_data.steps_photo_pages[step.id]
        photo_pages_data = make_photo_pages_data(photo_pages)

        hidden_photos = context.photo_data.steps_hidden_photos[step.id]

        cover_photo = context.photo_data.steps_cover_photos[step.id]

        step_context = StepContext(
            step=step,
            cover_photo=cover_photo,
            step_index=idx,
            steps=steps,
            trip=context.config.trip,
        )
        step_data = prepare_step_template(
            step_context,
            use_step_range=context.use_step_range,
        )
        step_data.photo_pages = photo_pages_data
        step_data.hidden_photos = hidden_photos
        steps_template_ctx.append(step_data)

    return steps_template_ctx


async def generate_album_html(
    steps: list[Step],
    photo_data: AlbumPhoto,
    config: AlbumGenerationConfig,
    locations: list[LocationEntry],
    *,
    use_step_range: bool = False,
) -> Path:
    """Generate HTML pages for the photo album."""
    context = GeneratorContext(
        steps=steps,
        photo_data=photo_data,
        config=config,
        use_step_range=use_step_range,
    )

    # Batch fetch all external data
    enriched_steps = await _enrich_steps(steps)

    # Prepare step data
    steps_template_ctx = _process_steps(context, enriched_steps)

    # Calculate trip overview
    trip_overview = calculate_trip_overview(
        steps=enriched_steps,
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
        light_mode=settings.light_mode,
        editor_mode=config.editor_mode,
        overview=trip_overview,
    )

    # Write output
    output_path = config.output_dir / "album.html"
    output_path.write_text(html, encoding="utf-8")

    return output_path
