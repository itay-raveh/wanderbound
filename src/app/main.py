"""Main CLI application for generating photo albums."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from rich import get_console

from src.album.generator import render_album_html
from src.app.edit import EditorServer
from src.core.cache import clear_cache
from src.core.logger import create_progress, get_logger
from src.core.text import is_hebrew
from src.data.context import TripTemplateCtx
from src.data.layout import AlbumLayout
from src.data.locations import PathPoint, load_locations
from src.data.trip import EnrichedStep, Step, Trip
from src.layout.processor import build_step_layout
from src.services.altitude import fetch_all_altitudes
from src.services.client import APIClient
from src.services.flags import fetch_flag
from src.services.maps import fetch_map
from src.services.weather import fetch_weather

from .args import Args

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from rich.progress import TaskID


logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


async def enrich_steps(steps: Sequence[Step]) -> Sequence[EnrichedStep]:
    """Fetch all external data concurrently."""
    with create_progress("earth") as progress:

        def _progress(task: TaskID, func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
            async def wrapper(*args: P.args, **kw: P.kwargs) -> T:
                res = await func(*args, **kw)
                progress.advance(task)
                return res

            return wrapper

        weather_progress = progress.add_task("Fetching weather data...", total=len(steps))
        flag_progress = progress.add_task("Fetching flags...", total=len(steps))
        map_progress = progress.add_task("Fetching maps...", total=len(steps))

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


def _gen_album_html_file(
    steps: Sequence[EnrichedStep],
    path_points: list[PathPoint],
    trip_template_ctx: TripTemplateCtx,
    output_dir: Path,
    *,
    edit: bool,
) -> Path:
    with get_console().status("[bold blue]Generating album HTML..."):
        html_path = render_album_html(
            steps,
            path_points,
            trip_template_ctx,
            output_dir,
            edit=edit,
        )
    logger.info("Generated: %s", html_path, extra={"success": True})
    return html_path


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


def _get_display_date_range(steps: Sequence[Step]) -> str:
    """Calculate and format the display date range for the trip."""
    start_date = min(s.date for s in steps)
    end_date = max(s.date for s in steps)

    return _format_date_range(start_date, end_date)


def _trip_cover_photo(trip_data: Trip, args: Args) -> str | None:
    """Resolve the cover photo path based on priority: CLI -> Local -> URL."""
    # 1. CLI Override
    if args.cover:
        return str(args.cover.absolute())

    if not trip_data.cover_photo:
        return None

    # 2. Local File Search
    if trip_data.cover_photo.uuid:
        uuid = trip_data.cover_photo.uuid
        # Search for the file in trip_dir
        found_photos = list(Path(args.trip).rglob(f"*{uuid}*.jpg"))
        if not found_photos:
            found_photos = list(Path(args.trip).rglob(f"*{uuid}*.jpg.jpg"))

        if found_photos:
            return str(found_photos[0].absolute())

    # 3. Remote URL
    return trip_data.cover_photo.path


def _update_layout_json_file(
    target_steps: Sequence[Step],
    trip_dir: Path,
    output_dir: Path,
) -> None:
    """Reloads step data, applying any layout overrides from layout.json."""
    layout_file = output_dir / "layout.json"

    layout = (
        AlbumLayout.model_validate_json(layout_file.read_bytes())
        if layout_file.exists()
        else AlbumLayout(steps={})
    )

    with create_progress() as progress:
        for step in progress.track(target_steps, description="Building layout.json..."):
            if step.id not in layout.steps:
                layout.steps[step.id] = build_step_layout(step, trip_dir)

    layout_file.write_text(layout.model_dump_json(indent=2))
    logger.info("Generated: %s", layout_file, extra={"success": True})


def main() -> None:
    args = Args(underscores_to_dashes=True).parse_args()

    trip_json_path = args.trip / "trip.json"
    if not trip_json_path.exists():
        logger.error(
            "trip.json not found at %s. Please ensure the trip directory contains trip.json",
            trip_json_path,
        )
        return

    logger.info("Found trip.json at %s", trip_json_path)

    if args.no_cache:
        clear_cache()
        logger.warning("Cleared cache")

    trip = Trip.model_validate_json(
        trip_json_path.read_text(encoding="utf-8"),
    )

    steps = asyncio.run(enrich_steps(args.filter_steps(trip.all_steps)))

    display_title = args.title or trip.name
    display_subtitle = args.subtitle or trip.summary
    cover = _trip_cover_photo(trip, args)

    min_time = steps[0].date.timestamp()
    max_time = (steps[-1].date + timedelta(days=1)).timestamp()
    path_points, path_segments = load_locations(args.trip, min_time, max_time)

    trip_template_ctx = TripTemplateCtx(
        title=display_title,
        title_dir="rtl" if is_hebrew(display_title) else "ltr",
        dates=_get_display_date_range(steps),
        subtitle=display_subtitle,
        subtitle_dir="rtl" if is_hebrew(display_subtitle) else "ltr",
        cover=cover,
        back_cover=str(args.back_cover.absolute()) if args.back_cover else cover,
        path_points=path_points,
        path_segments=path_segments,
    )

    args.output.mkdir(parents=True, exist_ok=True)

    _update_layout_json_file(steps, args.trip, args.output)

    # Initial Generation
    _gen_album_html_file(steps, path_points, trip_template_ctx, args.output, edit=True)

    if True:
        logger.info("Starting Editor Mode...")

        def regenerate_callback(target_ids: Sequence[int]) -> None:
            logger.info("Updating steps %s", target_ids)
            _update_layout_json_file(
                [step for step in steps if step.id in target_ids], args.trip, args.output
            )
            _gen_album_html_file(
                steps,
                path_points,
                trip_template_ctx,
                args.output,
                edit=True,
            )

        EditorServer(args.output, args.trip, regenerate_callback).run()
