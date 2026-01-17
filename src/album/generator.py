"""Generate HTML pages for the photo album using Jinja templates."""

import operator
from collections.abc import Iterable, Sequence
from functools import reduce
from pathlib import Path

from geopy.distance import distance
from jinja2 import Environment, FileSystemLoader

from src.core.logger import get_logger
from src.core.settings import settings
from src.data.context import MapTemplateCtx, OverviewTemplateCtx, TripTemplateCtx
from src.data.layout import AlbumLayout
from src.data.segments import PathPoint, Segment
from src.data.trip import EnrichedStep, Step

from .preparation import build_step_template_ctx

logger = get_logger(__name__)


def render_album_html(
    steps: Sequence[EnrichedStep],
    trip_ctx: TripTemplateCtx,
    maps_slices: list[slice[int]],
    output_dir: Path,
) -> Path:
    """Generate HTML pages for the photo album."""
    layout = AlbumLayout.model_validate_json((output_dir / "layout.json").read_bytes())

    steps_ctx = [
        build_step_template_ctx(
            step,
            layout.steps[step.id],
            idx,
            steps,
        )
        for idx, step in enumerate(steps)
    ]

    main_map_ctx = MapTemplateCtx(
        id="map-main",
        segments=trip_ctx.segments,
        steps=steps_ctx,
    )

    submaps_ctx = {
        map_slice.start: MapTemplateCtx(
            id=f"map-{map_slice.start}-{map_slice.stop - 1}",
            segments=(
                _filter_segments(
                    trip_ctx.segments,
                    steps[map_slice][0].start_time,
                    steps[map_slice][-1].start_time + 3600 * 24,
                )
            ),
            steps=steps_ctx[map_slice],
        )
        for map_slice in maps_slices
    }

    overview_ctx = _gen_overview_template_ctx(steps, layout, trip_ctx.segments)

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
        main_map=main_map_ctx,
        submaps=submaps_ctx,
    )

    output_path = output_dir / "album.html"
    output_path.write_text(html, encoding="utf-8")

    return output_path


def _filter_segments(segments: list[Segment], min_time: float, max_time: float) -> list[Segment]:
    """Return segments that overlap with the time window."""
    filtered: list[Segment] = []

    for seg in segments:
        valid_points = [point for point in seg.points if min_time <= point.time <= max_time]

        if len(valid_points) < 2:
            continue

        filtered.append(Segment(points=valid_points, is_flight=seg.is_flight))

    return filtered


def _gen_overview_template_ctx(
    steps: Sequence[Step],
    layout: AlbumLayout,
    segments: list[Segment],
) -> OverviewTemplateCtx:
    countries = {
        step.location.country: settings.flag_cdn_url.format(
            country_code=step.location.country_code.lower()
        )
        for step in steps
    }

    points: Iterable[PathPoint] = reduce(  # pyright: ignore[reportAny]
        operator.iadd, (segment.points for segment in segments), []
    )
    pairs = ((location.lat, location.lon) for location in points)
    total_dist = distance(*pairs)

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
