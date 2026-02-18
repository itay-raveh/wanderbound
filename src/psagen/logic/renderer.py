from __future__ import annotations

import operator
from functools import reduce
from typing import TYPE_CHECKING

from geopy.distance import distance
from geopy.point import Point
from jinja2 import Environment, FileSystemLoader

from psagen.core.logger import get_logger
from psagen.core.settings import settings
from psagen.core.text import choose_text_dir, find_visual_split_index
from psagen.logic.segments import PathPoint, Segment
from psagen.models.config import AlbumSettings, Slice
from psagen.models.context import (
    FurthestPointCtx,
    MapTemplateCtx,
    OverviewTemplateCtx,
    StepTemplateCtx,
    TripTemplateCtx,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import datetime

    from psagen.models.enrich import EnrichedStep
    from psagen.models.layout import StepLayout
    from psagen.models.trip import Location, Step

logger = get_logger(__name__)

env = Environment(
    loader=FileSystemLoader(str(settings.static_dir)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

env.filters["text_dir"] = choose_text_dir

_ALBUM_TEMPLATE = env.get_template("album.html.jinja")


def render_album_html(
    album_settings: AlbumSettings,
    layouts: dict[int, StepLayout],
    steps: list[EnrichedStep],
    segments: list[Segment],
) -> str:
    trip_ctx = TripTemplateCtx(
        title=album_settings.title,
        subtitle=album_settings.subtitle or "",
        dates=_format_date_range(steps[0].date, steps[-1].date),
        cover=album_settings.front_cover_photo,
        back_cover=album_settings.back_cover_photo,
        segments=segments,
    )

    overview_ctx = _build_overview_template_ctx(steps, layouts, segments, album_settings.home)

    steps_ctx = [
        _build_step_template_ctx(
            step,
            layouts[step.id],
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
            id=f"map-{map_slice}",
            segments=_segments_for_steps(steps[map_slice.as_slice()], trip_ctx.segments),
            steps=steps_ctx[map_slice.as_slice()],
        )
        for map_slice in _re_indexed_maps_slices(
            album_settings.steps_ranges.root, album_settings.maps_ranges.root
        )
    }

    return _ALBUM_TEMPLATE.render(
        trip=trip_ctx,
        steps=steps_ctx,
        overview=overview_ctx,
        main_map=main_map_ctx,
        submaps=submaps_ctx,
    )


def _re_indexed_maps_slices(steps: list[Slice], maps: list[Slice]) -> list[Slice]:
    if not maps:
        return []

    # Build mapping from Original Index -> Filtered Index
    idx_map: dict[int, int] = {}
    current_idx = 0
    for slc in steps:
        for orig_idx in range(slc.start, slc.end):
            idx_map[orig_idx] = current_idx
            current_idx += 1

    maps_slices: list[Slice] = []
    for map_slice in maps:
        if map_slice.start not in idx_map:
            raise ValueError(f"Map start index {map_slice.start} is not in the included steps!")

        # slice.stop is exclusive
        last_included_orig = map_slice.end - 1
        if last_included_orig not in idx_map:
            raise ValueError(f"Map end index {last_included_orig} is not in the included steps!")

        maps_slices.append(Slice(start=idx_map[map_slice.start], end=idx_map[last_included_orig]))

    return maps_slices


def _segments_for_steps(steps: Sequence[Step], all_segments: list[Segment]) -> list[Segment]:
    # For a single step, grab the whole day
    if len(steps) == 1:
        min_time = steps[0].date.replace(hour=0).timestamp()
        max_time = steps[0].date.replace(hour=23).timestamp()
    # Otherwise, grab between the steps
    else:
        min_time = steps[0].date.timestamp()
        max_time = steps[-1].date.timestamp()

    filtered: list[Segment] = []

    for segment in all_segments:
        valid_points = [point for point in segment.points if min_time <= point.time <= max_time]

        if len(valid_points) < 2:
            continue

        filtered.append(Segment(points=valid_points, is_flight=segment.is_flight))

    return filtered


def _format_date_range(start: datetime, end: datetime) -> str:
    """Format date range smartly, omitting redundant year/month."""
    if start.year == end.year:
        if start.month == end.month:
            # Same month and year: "16 - 26 April 2025"
            return f"{start.day} - {end.day} {start.strftime('%B %Y')}"
        # Different month, same year: "16 April - 2 May 2025"
        return f"{start.day} {start.strftime('%B')} - {end.day} {end.strftime('%B %Y')}"

    # Different year: "28 December 2024 - 15 January 2025"
    return f"{start.day} {start.strftime('%B %Y')} - {end.day} {end.strftime('%B %Y')}"


def _build_step_template_ctx(
    step: EnrichedStep,
    layout: StepLayout,
    step_index: int,
    steps: Sequence[EnrichedStep],
) -> StepTemplateCtx:
    progress = 100 * step_index / (len(steps) - 1) if len(steps) > 1 else 0

    lat_str, lon_str = (
        Point(round(step.location.lat, 3), round(step.location.lon, 3)).format_unicode().split(",")
    )

    description = step.description
    extra_description: str | None = None

    if step.is_extra_long_description:
        split_idx = find_visual_split_index(description, settings.extra_long_description_threshold)
        extra_description = description[split_idx:].strip()
        description = description[:split_idx].strip()

    return StepTemplateCtx(
        id=step.id,
        index=step_index,
        name=step.name,
        country=step.location.country,
        lat_str=lat_str,
        lon_str=lon_str,
        lat_val=step.location.lat,
        lon_val=step.location.lon,
        date_month=step.date.strftime("%B"),
        date_day=str(step.date.day),
        day_weather_icon_url=settings.weather_icon_url.format(icon_name=step.weather.day.icon),
        night_weather_icon_url=(
            settings.weather_icon_url.format(icon_name=step.weather.night.icon)
            if step.weather.night
            else ""
        ),
        temp_str=_format_temperature(step.weather.day.temp, step.weather.day.feels_like),
        temp_night_str=(
            _format_temperature(step.weather.night.temp, step.weather.night.feels_like)
            if step.weather.night
            else ""
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
        extra_description=extra_description,
        is_long_description=step.is_long_description,
        photo_pages=layout.pages,
        hidden_photos=layout.hidden_photos,
    )


def _format_temperature(temp: float, feels_like: float) -> str:
    if abs(feels_like - temp) >= settings.feels_like_display_threshold:
        return f"{int(temp)}° ({int(feels_like)}°)"
    return f"{int(temp)}°"


def _build_overview_template_ctx(
    steps: Sequence[Step],
    layouts: dict[int, StepLayout],
    segments: list[Segment],
    home: Location | None,
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

    photo_count = sum(
        sum(len(page.photos) for page in step_layout.pages)
        for step_layout in layouts.values()
        if step_layout.id in [step.id for step in steps]
    )

    furthest_point = None
    if home:
        furthest_point = _calculate_furthest_point(steps, home)

    return OverviewTemplateCtx(
        countries=list(countries.items()),
        total_km=f"{round(total_dist.km):,}",
        total_days=f"{(steps[-1].date - steps[0].date).days + 1:,}",
        step_count=f"{len(steps):,}",
        photo_count=f"{photo_count:,}",
        furthest_point=furthest_point,
    )


def _calculate_furthest_point(steps: Sequence[Step], home: Location) -> FurthestPointCtx:
    max_dist = 0.0
    furthest_step = steps[0]

    for step in steps:
        dist = distance((home.lat, home.lon), (step.location.lat, step.location.lon)).km
        if dist > max_dist:
            max_dist = dist
            furthest_step = step

    return FurthestPointCtx(
        home=home,
        furthest=furthest_step.location,
        distance_km=f"{round(max_dist):,}",
    )
