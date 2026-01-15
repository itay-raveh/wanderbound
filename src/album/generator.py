"""Generate HTML pages for the photo album using Jinja templates."""

from collections.abc import Sequence
from pathlib import Path

from geopy.distance import distance
from jinja2 import Environment, FileSystemLoader

from src.core.logger import get_logger
from src.core.settings import settings
from src.data.context import OverviewTemplateCtx, TripTemplateCtx
from src.data.layout import AlbumLayout
from src.data.locations import PathPoint
from src.data.trip import EnrichedStep, Step

from .preparation import build_step_template_ctx

logger = get_logger(__name__)


def render_album_html(
    steps: Sequence[EnrichedStep],
    path_points: list[PathPoint],
    trip_ctx: TripTemplateCtx,
    output_dir: Path,
) -> Path:
    """Generate HTML pages for the photo album."""
    layout_file = output_dir / "layout.json"
    layout = AlbumLayout.model_validate_json(layout_file.read_bytes())

    steps_ctx = [
        build_step_template_ctx(
            step,
            layout.steps[step.id],
            idx,
            steps,
        )
        for idx, step in enumerate(steps)
    ]

    overview_ctx = _gen_overview_template_ctx(steps, layout, path_points)

    template_dir = Path(__file__).parents[2] / "static"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    html = env.get_template("album.html.jinja").render(
        trip=trip_ctx,
        steps=steps_ctx,
        light_mode=settings.light_mode,
        overview=overview_ctx,
    )

    output_path = output_dir / "album.html"
    output_path.write_text(html, encoding="utf-8")

    return output_path


def _gen_overview_template_ctx(
    steps: Sequence[Step],
    layout: AlbumLayout,
    path_points: list[PathPoint],
) -> OverviewTemplateCtx:
    countries = {
        step.location.country: settings.flag_cdn_url.format(
            country_code=step.location.country_code.lower()
        )
        for step in steps
    }

    total_dist = distance(*((location.lat, location.lon) for location in path_points))

    return OverviewTemplateCtx(
        countries=list(countries.items()),
        total_km=f"{round(total_dist.km):,}",
        total_days=(steps[-1].date - steps[0].date).days,
        step_count=len(steps),
        photo_count=sum(
            sum(len(page.photos) for page in step_layout.pages)
            for step_layout in layout.steps.values()
        ),
    )
