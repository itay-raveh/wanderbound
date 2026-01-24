from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.app.renderer import build_overview_template_ctx, render_album_html
from src.app.state import state
from src.core.cache import clear_cache
from src.core.logger import create_progress, get_console, get_logger
from src.core.text import choose_text_dir
from src.layout.builder import build_step_layout
from src.models.context import TripTemplateCtx
from src.models.layout import AlbumLayout
from src.models.segments import load_segments
from src.models.trip import EnrichedStep, Trip
from src.services.altitude import fetch_all_altitudes
from src.services.client import APIClient
from src.services.flags import fetch_flag
from src.services.location import fetch_home_location
from src.services.maps import fetch_map
from src.services.weather import fetch_weather

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence
    from datetime import datetime

    from rich.progress import TaskID

    from src.models.args import GeneratorArgs
    from src.models.trip import Step, TripCover

logger = get_logger(__name__)


async def _enrich_steps(steps: Sequence[Step]) -> Sequence[EnrichedStep]:
    """Fetch all external data concurrently."""
    with create_progress("Fetching online data") as progress:
        def _progress[**P, T](
                task: TaskID, func: Callable[P, Awaitable[T]]
        ) -> Callable[P, Awaitable[T]]:
            async def wrapper(*args: P.args, **kw: P.kwargs) -> T:
                res = await func(*args, **kw)
                progress.advance(task)
                return res

            return wrapper

        weather_progress = progress.add_task("Weather...", total=len(steps))
        flag_progress = progress.add_task("Flags...", total=len(steps))
        map_progress = progress.add_task("Maps...", total=len(steps))

        async with APIClient() as client:
            results = await asyncio.gather(
                *(
                    asyncio.gather(
                        _progress(weather_progress, fetch_weather)(
                            client, step.location.lat, step.location.lon, step.date
                        ),
                        _progress(flag_progress, fetch_flag)(client, step.location.country_code),
                        _progress(map_progress, fetch_map)(
                            client, step.location.lat, step.location.lon, step.location.country_code
                        ),
                    )
                    for step in steps
                ),
            )

            alts = await fetch_all_altitudes(
                client, [(step.location.lat, step.location.lon) for step in steps]
            )

    logger.info("Enriched %d steps", len(steps))

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


def _select_trip_cover(trip_cover: TripCover, args: GeneratorArgs) -> str | None:
    """Resolve the cover photo path based on priority: CLI -> Local -> URL."""
    # 1. CLI / Form Override
    if args.cover:
        return str(args.cover.absolute())

    # 2. Local File Search
    if photos := list(args.trip.rglob(f"*{trip_cover.uuid}*.jpg")):
        return str(photos[0].absolute())

    # 3. Remote URL
    return trip_cover.url


async def _trip_template_ctx(
        args: GeneratorArgs, trip: Trip, steps: Sequence[Step]
) -> TripTemplateCtx:
    title = args.title or trip.title
    subtitle = args.subtitle or trip.subtitle
    cover = _select_trip_cover(trip.cover_photo, args)
    back_cover = str(args.back_cover.absolute()) if args.back_cover else cover

    start_date = steps[0].date
    end_date = steps[-1].date

    segments = load_segments(
        args.trip,
        [(step.location.lat, step.location.lon, step.start_time) for step in steps],
        start_date.timestamp(),
        # Go until the END of the last day
        end_date.timestamp() + 60 * 60 * 24,
    )

    logger.info("Loaded %d travel segments", len(segments))

    return TripTemplateCtx(
        title=title,
        title_dir=choose_text_dir(title),
        subtitle=subtitle,
        subtitle_dir=choose_text_dir(subtitle),
        dates=_format_date_range(start_date, end_date),
        cover=cover,
        back_cover=back_cover,
        segments=segments,
    )


async def generate_step_layouts(target_ids: Sequence[int]) -> None:
    """Generate layout and HTML for specific steps."""
    logger.info("Generating steps %s", target_ids)

    layout = (
        AlbumLayout.model_validate_json(state.layout_file.read_bytes())
        if state.layout_file.exists()
        else AlbumLayout(steps={})
    )

    with create_progress("Loading photos/videos") as progress:
        steps_to_process = [step for step in state.steps if step.id in target_ids]

        for step in progress.track(steps_to_process, description="Building layouts..."):
            if step.id not in layout.steps:
                layout.steps[step.id] = await build_step_layout(
                    step, state.args.trip, state.args.output
                )

    state.layout_file.write_text(layout.model_dump_json(indent=2))
    logger.info("Generated: %s", state.layout_file, extra={"success": True})

    if not state.trip_ctx or not state.home_location:
        logger.warning("Missing context for HTML generation")
        return

    overview_ctx = build_overview_template_ctx(
        state.steps, layout, state.trip_ctx.segments, state.home_location
    )

    with get_console().status("[bold blue]Generating HTML..."):
        html = render_album_html(
            state.steps, layout, state.trip_ctx, overview_ctx, state.args.maps or []
        )

    html_file = state.args.output / "album.html"
    html_file.write_text(html)
    logger.info("Generated: %s", html_file, extra={"success": True})


async def run_generation_task(args: GeneratorArgs) -> None:
    """Main entry point for generation process."""
    if args.no_cache:
        clear_cache()
        logger.warning("Cleared cache")

    trip_file = args.trip / "trip.json"

    if not trip_file.exists():
        logger.error("trip.json not found in %s", args.trip)
        return

    trip = Trip.model_validate_json(trip_file.read_text())

    if args.steps:
        logger.info("Filtered to steps %r", args.steps)
        target_steps = sum((trip.all_steps[slc] for slc in args.steps), start=[])
    else:
        logger.info("Using all %d steps", len(trip.all_steps))
        target_steps = trip.all_steps

    steps = await _enrich_steps(target_steps)
    trip_ctx = await _trip_template_ctx(args, trip, steps)
    home_location = await fetch_home_location()

    # Update Global State
    state.args = args
    state.trip_ctx = trip_ctx
    state.steps = steps
    state.home_location = home_location
    state.layout_file = args.output / "layout.json"

    # Initial Generation
    await generate_step_layouts([step.id for step in steps])
