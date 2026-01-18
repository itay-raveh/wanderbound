"""Main CLI application for generating photo albums."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from src.core.cache import clear_cache
from src.core.logger import create_progress, get_logger
from src.core.text import choose_text_dir
from src.models.context import TripTemplateCtx
from src.models.segments import load_segments
from src.models.trip import EnrichedStep, Step, Trip, TripCover
from src.services.altitude import fetch_all_altitudes
from src.services.client import APIClient
from src.services.flags import fetch_flag
from src.services.location import fetch_home_location
from src.services.maps import fetch_map
from src.services.weather import fetch_weather

from .args import Args
from .server import EditorServer

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence
    from datetime import datetime

    from rich.progress import TaskID


logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


async def _enrich_steps(steps: Sequence[Step]) -> Sequence[EnrichedStep]:
    """Fetch all external data concurrently."""
    with create_progress("Fetching online data", "earth") as progress:

        def _progress(task: TaskID, func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
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


def _select_trip_cover(trip_cover: TripCover, args: Args) -> str | None:
    """Resolve the cover photo path based on priority: CLI -> Local -> URL."""
    # 1. CLI Override
    if args.cover:
        return str(args.cover.absolute())

    # 2. Local File Search
    if photos := list(args.trip.rglob(f"*{trip_cover.uuid}*.jpg")):
        return str(photos[0].absolute())

    # 3. Remote URL
    return trip_cover.url


async def _trip_template_ctx(args: Args, trip: Trip, steps: Sequence[Step]) -> TripTemplateCtx:
    title = args.title or trip.title
    subtitle = args.subtitle or trip.subtitle
    cover = _select_trip_cover(trip.cover_photo, args)
    back_cover = str(args.back_cover.absolute()) if args.back_cover else cover

    start_date = steps[0].date
    end_date = steps[-1].date

    segments = load_segments(
        args.trip,
        steps,
        start_date.timestamp(),
        # Go until the END of the last day
        end_date.timestamp() + 60 * 60 * 24,
    )

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


async def make_server() -> EditorServer | None:
    args = Args(underscores_to_dashes=True).parse_args(known_only=True)

    if args.no_cache:
        clear_cache()
        logger.warning("Cleared cache")

    trip_file = args.trip / "trip.json"
    if not trip_file.exists():
        logger.error("trip.json not found at %s.", trip_file)
        return None
    trip = Trip.model_validate_json(trip_file.read_text())

    target_steps = args.filter_steps(trip.all_steps)
    maps_slices = args.filter_map_slices(target_steps)
    if maps_slices is None:
        return None

    steps = await _enrich_steps(target_steps)
    trip_ctx = await _trip_template_ctx(args, trip, steps)
    home_location = await fetch_home_location()

    args.output.mkdir(parents=True, exist_ok=True)
    server = EditorServer(args, trip_ctx, steps, maps_slices, home_location)
    await server.generate([step.id for step in steps])
    return server


def main() -> None:
    if server := asyncio.run(make_server()):
        server.run()
