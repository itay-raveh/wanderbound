"""Generate HTML pages for the photo album using Jinja templates."""

from collections.abc import Sequence
from pathlib import Path

from geopy.distance import distance
from jinja2 import Environment, FileSystemLoader

from src.core.logger import get_logger
from src.core.settings import settings
from src.data.context import OverviewTemplateCtx, StepTemplateCtx, TripTemplateCtx
from src.data.locations import PathPoint
from src.data.models import (
    AlbumPhoto,
    Step,
    StepContext,
)
from src.data.trip import EnrichedStep

from .assets import make_photo_pages_data
from .preparation import prepare_step_template

logger = get_logger(__name__)


def generate_album_html(
    steps: Sequence[EnrichedStep],
    photo_data: AlbumPhoto,
    path_points: list[PathPoint],
    trip_template_ctx: TripTemplateCtx,
    output_dir: Path,
    *,
    edit: bool,
) -> Path:
    """Generate HTML pages for the photo album."""
    steps_template_ctx = _process_steps(steps, photo_data)

    overview = _gen_overview(
        steps=steps,
        photo_data=photo_data,
        path_points=path_points,
    )

    template_dir = Path(__file__).parents[2] / "static"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    html = env.get_template("album.html.jinja").render(
        trip=trip_template_ctx,
        steps=steps_template_ctx,
        light_mode=settings.light_mode,
        edit=edit,
        overview=overview,
    )

    # Write output
    output_path = output_dir / "album.html"
    output_path.write_text(html, encoding="utf-8")

    return output_path


def _process_steps(
    steps: Sequence[EnrichedStep],
    photo_data: AlbumPhoto,
) -> list[StepTemplateCtx]:
    """Process steps and prepare data for rendering."""
    steps_template_ctx: list[StepTemplateCtx] = []

    for idx, step in enumerate(steps):
        photo_pages = photo_data.steps_photo_pages[step.id]
        photo_pages_data = make_photo_pages_data(photo_pages)

        hidden_photos = photo_data.steps_hidden_photos[step.id]

        cover_photo = photo_data.steps_cover_photos[step.id]

        step_context = StepContext(
            step=step,
            cover_photo=cover_photo,
            step_index=idx,
            steps=steps,
        )
        step_data = prepare_step_template(
            step_context,
        )
        step_data.photo_pages = photo_pages_data
        step_data.hidden_photos = hidden_photos
        steps_template_ctx.append(step_data)

    return steps_template_ctx


def _gen_overview(
    steps: Sequence[Step],
    photo_data: AlbumPhoto,
    path_points: list[PathPoint],
) -> OverviewTemplateCtx:
    countries = {
        step.location.country: settings.flag_cdn_url.format(
            country_code=step.location.country_code.lower()
        )
        for step in steps
    }

    logger.info("Calculating distance between %d points", len(path_points))

    total_dist = distance(*((location.lat, location.lon) for location in path_points))

    return OverviewTemplateCtx(
        countries=list(countries.items()),
        total_km=f"{round(total_dist.km):,}",
        total_days=(steps[-1].date - steps[0].date).days,
        step_count=len(steps),
        photo_count=sum(map(len, photo_data.steps_with_photos.values())),
    )
