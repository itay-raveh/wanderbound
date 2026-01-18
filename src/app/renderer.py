"""Generate HTML pages for the photo album using Jinja templates."""

import operator
from collections.abc import Iterable, Sequence
from functools import reduce
from pathlib import Path

from geopy.distance import distance
from geopy.point import Point
from jinja2 import Environment, FileSystemLoader

from src.core.logger import get_logger
from src.core.settings import settings
from src.core.text import choose_text_dir, find_visual_split_index
from src.models.context import MapTemplateCtx, OverviewTemplateCtx, StepTemplateCtx, TripTemplateCtx
from src.models.layout import AlbumLayout, StepLayout
from src.models.segments import PathPoint, Segment
from src.models.trip import EnrichedStep, Step

logger = get_logger(__name__)


def render_album_html(
    steps: Sequence[EnrichedStep],
    layout: AlbumLayout,
    trip_ctx: TripTemplateCtx,
    maps_slices: list[slice[int]],
) -> str:
    """Generate HTML pages for the photo album."""
    steps_ctx = [
        _build_step_template_ctx(
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
        steps=[],
    )

    submaps_ctx = {
        map_slice.start: MapTemplateCtx(
            id=f"map-{map_slice.start}-{map_slice.stop - 1}",
            segments=_filter_segments(steps[map_slice], trip_ctx.segments),
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

    return env.get_template("album.html.jinja").render(
        trip=trip_ctx,
        steps=steps_ctx,
        light_mode=settings.light_mode,
        overview=overview_ctx,
        main_map=main_map_ctx,
        submaps=submaps_ctx,
    )


def _filter_segments(steps: Sequence[Step], segments: list[Segment]) -> list[Segment]:
    """Return segments that overlap with the time window."""
    min_time = steps[0].date.timestamp()
    max_time = steps[-1].date.timestamp()

    if len(steps) == 1:
        # Single step, grab around it
        min_time -= 6 * 3600
        max_time += 6 * 3600

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


def _build_step_template_ctx(
    step: EnrichedStep,
    layout: StepLayout,
    step_index: int,
    steps: Sequence[EnrichedStep],
) -> StepTemplateCtx:
    progress = 100 * step_index / (len(steps) - 1) if len(steps) > 1 else 0
    coords_lat, coords_lon = str(
        Point(round(step.location.lat, 4), round(step.location.lon, 4)).format_unicode()
    ).split(",")

    description = step.description
    extra_description: str | None = None

    if step.is_extra_long_description:
        # Split using visual length calculation
        split_idx = find_visual_split_index(description, settings.extra_long_description_threshold)

        extra_description = description[split_idx:].strip()
        description = description[:split_idx].strip()

    return StepTemplateCtx(
        id=step.id,
        index=step_index,
        name=step.name,
        country=step.location.country,
        coords_lat=coords_lat,
        coords_lon=coords_lon,
        lat_val=step.location.lat,
        lon_val=step.location.lon,
        date_month=step.date.strftime("%B"),
        date_day=str(step.date.day),
        day_weather_icon_url=(settings.weather_icon_url.format(icon_name=step.weather.day_icon)),
        night_weather_icon_url=(
            settings.weather_icon_url.format(icon_name=step.weather.night_icon)
        ),
        temp_str=(_format_temperature(step.weather.day_temp, step.weather.day_feels_like)),
        temp_night_str=(
            _format_temperature(step.weather.night_temp, step.weather.night_feels_like)
        ),
        altitude_str=f"{round(step.altitude):,}",
        progress_percent=progress,
        day_counter_box_position=max(6.0, min(progress, 94.0)),
        day_counter_arrow_position=max(1.0, min(progress, 99.0)),
        cover_photo=layout.cover,
        country_flag_data_uri=step.flag.flag_url,
        country_map_svg=step.map.svg_content,
        map_dot_x=step.map.dot_position[0],
        map_dot_y=step.map.dot_position[1],
        accent_color=step.flag.accent_color,
        description=description,
        desc_dir=choose_text_dir(step.description),
        extra_description=extra_description,
        is_long_description=len(step.description) > settings.long_description_threshold,
        photo_pages=layout.pages,
        hidden_photos=layout.hidden_photos,
    )


def _format_temperature(temp: float | None, feels_like: float | None) -> str:
    if temp is None:
        return "N/A"
    if feels_like is not None and abs(feels_like - temp) >= settings.feels_like_display_threshold:
        return f"{int(temp)}° ({int(feels_like)}°)"
    return f"{int(temp)}°"
