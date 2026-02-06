from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from nicegui import app

from psagen.core.cache import force_cache_update
from psagen.core.logger import create_progress, get_console, get_logger
from psagen.logic.altitude import fetch_all_altitudes
from psagen.logic.client import APIClient
from psagen.logic.flags import fetch_flag
from psagen.logic.location import fetch_home_location
from psagen.logic.maps import fetch_map
from psagen.logic.media import extract_frame, frame_path, load_photo
from psagen.logic.renderer import build_overview_template_ctx, render_album_html
from psagen.logic.weather import get_weather_with_fallback
from psagen.models.args import GeneratorArgs, str_slices
from psagen.models.builder import build_step_layout, try_build_layout
from psagen.models.context import TripTemplateCtx
from psagen.models.layout import AlbumLayout, Video
from psagen.models.segments import load_segments, simplify_segments
from psagen.models.trip import EnrichedStep, Location, Trip, Weather

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence
    from datetime import datetime

    from rich.progress import TaskID

    from psagen.models.layout import StepLayout
    from psagen.models.trip import Step, TripCover

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
            # Create weather fetch coroutines with fallback support
            async def fetch_step_weather(step: Step) -> Weather:
                weather_temp = step.weather_info.temperature if step.weather_info else None
                weather_cond = step.weather_info.conditions if step.weather_info else None
                result = await get_weather_with_fallback(
                    client,
                    step.location.lat,
                    step.location.lon,
                    step.date,
                    trip_weather_temp=weather_temp,
                    trip_weather_conditions=weather_cond,
                )
                progress.advance(weather_progress)
                return result

            results = await asyncio.gather(
                *(
                    asyncio.gather(
                        fetch_step_weather(step),
                        _progress(flag_progress, fetch_flag)(client, step.location.country_code),
                        _progress(map_progress, fetch_map)(
                            client,
                            step.location.lat,
                            step.location.lon,
                            step.location.country_code,
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


def _trip_template_ctx(args: GeneratorArgs, trip: Trip, steps: Sequence[Step]) -> TripTemplateCtx:
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
        subtitle=subtitle,
        dates=_format_date_range(start_date, end_date),
        cover=cover,
        back_cover=back_cover,
        segments=segments,
        main_map_segments=simplify_segments(segments),
    )


class AlbumService:
    def __init__(
        self,
        args: GeneratorArgs,
        trip_ctx: TripTemplateCtx,
        steps: Sequence[EnrichedStep],
        home_location: tuple[Location, str],
        layout_file: Path,
    ) -> None:
        self.args = args
        self.trip_ctx = trip_ctx
        self.steps = steps
        self.home_location = home_location
        self.layout_file = layout_file

    @classmethod
    async def from_args(cls, args: GeneratorArgs) -> AlbumService:
        """Load album state from disk and external services."""
        trip_file = args.trip / "trip.json"
        if not trip_file.exists():
            raise FileNotFoundError(f"trip.json not found in {args.trip}")

        trip_json = await asyncio.to_thread(trip_file.read_text, encoding="utf-8")
        trip = Trip.model_validate_json(trip_json)

        if args.steps:
            logger.info("Filtered to steps %s", str_slices(args.steps))
            target_steps = sum((trip.all_steps[slc] for slc in args.steps), start=[])  # pyright: ignore[reportUnknownArgumentType]
        else:
            logger.info("Using all %d steps", len(trip.all_steps))
            target_steps = trip.all_steps

        if args.no_cache:
            logger.info("Forcing cache update for external data")
            with force_cache_update():
                steps = await _enrich_steps(target_steps)
        else:
            steps = await _enrich_steps(target_steps)

        trip_ctx = _trip_template_ctx(args, trip, steps)
        home_location = await fetch_home_location()

        return cls(
            args=args,
            trip_ctx=trip_ctx,
            steps=steps,
            home_location=home_location,
            layout_file=args.output / "layout.json",
        )

    async def generate(self) -> None:
        """Generate the album layout and HTML."""
        await self._generate_for_steps([step.id for step in self.steps])

    async def update_cover(self, step_id: int, new_cover: str) -> None:
        layout_json = await asyncio.to_thread(self.layout_file.read_text, encoding="utf-8")
        layout = AlbumLayout.model_validate_json(layout_json)

        step_layout = layout.steps[step_id]
        old_cover = step_layout.cover
        step_layout.cover = Path(new_cover)

        # if the old cover was not in any of the pages
        if not any(
            old_cover in [photo.path for photo in page.photos] for page in step_layout.pages
        ):
            # then we need to find the page with the new cover,
            # and replace it with the old cover
            for page in step_layout.pages:
                for idx, photo in enumerate(page.photos):
                    if photo.path == step_layout.cover:
                        page.photos[idx] = await load_photo(old_cover)
                        break

        await asyncio.to_thread(
            self.layout_file.write_text, layout.model_dump_json(indent=2), encoding="utf-8"
        )
        await self._generate_for_steps([step_id])

    async def update_video_timestamp(self, step_id: int, src: str, timestamp: float) -> None:
        layout_json = await asyncio.to_thread(self.layout_file.read_text, encoding="utf-8")
        layout = AlbumLayout.model_validate_json(layout_json)

        src_path = Path(src)

        for page in layout.steps[step_id].pages:
            for photo in page.photos:
                if isinstance(photo, Video) and photo.src == src_path:
                    photo.path = frame_path(src_path, timestamp, self.args.output)
                    photo.timestamp = timestamp
                    await extract_frame(photo.src, photo.timestamp, photo.path)
                    break

        await asyncio.to_thread(
            self.layout_file.write_text, layout.model_dump_json(indent=2), encoding="utf-8"
        )
        await self._generate_for_steps([step_id])

    async def update_layout(self, updates: list[StepLayout]) -> None:
        layout_json = await asyncio.to_thread(self.layout_file.read_text, encoding="utf-8")
        layout = AlbumLayout.model_validate_json(layout_json)

        for step_layout in updates:
            step_layout.pages = [
                try_build_layout(page_layout.photos) or page_layout
                for page_layout in step_layout.pages
            ]
            layout.steps[step_layout.id] = step_layout

        await asyncio.to_thread(
            self.layout_file.write_text, layout.model_dump_json(indent=2), encoding="utf-8"
        )
        await self._generate_for_steps([step_layout.id for step_layout in updates])

    async def _generate_for_steps(self, target_ids: Sequence[int]) -> None:
        """Generate layout and HTML for specific steps."""
        logger.info("Generating steps %s", target_ids)

        if self.layout_file.exists():
            layout_json = await asyncio.to_thread(self.layout_file.read_text, encoding="utf-8")
            layout = AlbumLayout.model_validate_json(layout_json)
        else:
            layout = AlbumLayout(steps={})

        with create_progress("Loading photos/videos") as progress:
            steps_to_process = [step for step in self.steps if step.id in target_ids]

            for step in progress.track(steps_to_process, description="Building layouts..."):
                if step.id not in layout.steps:
                    layout.steps[step.id] = await build_step_layout(
                        step, self.args.trip, self.args.output
                    )

        await asyncio.to_thread(
            self.layout_file.write_text, layout.model_dump_json(indent=2), encoding="utf-8"
        )
        logger.info("Generated: %s", self.layout_file, extra={"success": True})

        overview_ctx = build_overview_template_ctx(
            self.steps, layout, self.trip_ctx.segments, self.home_location
        )

        with get_console().status("[bold blue]Generating HTML..."):
            html = await asyncio.to_thread(
                render_album_html,
                self.steps,
                layout,
                self.trip_ctx,
                overview_ctx,
                self.args.maps or [],
            )

        html_file = self.args.output / "album.html"
        await asyncio.to_thread(html_file.write_text, html, encoding="utf-8")
        logger.info("Generated: %s", html_file, extra={"success": True})


def get_generator_args() -> GeneratorArgs:
    """Dependency to get generator arguments from storage."""
    return GeneratorArgs.model_validate(
        {k: (None if v == "" else v) for k, v in app.storage.user.items()}
    )


async def get_album_service(
    args: Annotated[GeneratorArgs, Depends(get_generator_args)],
) -> AlbumService:
    """Dependency for FastAPI to get the album service."""
    # Check if current singleton matches the requested args
    current: AlbumService | None = getattr(app.state, "album_service", None)
    if current and current.args == args:
        return current

    # If not, recreate it
    app.state.album_service = await AlbumService.from_args(args)
    return app.state.album_service


def try_get_generator_args() -> GeneratorArgs | None:
    """Dependency to get generator arguments from storage if valid."""
    try:
        return get_generator_args()
    except ValueError:
        return None


async def try_get_album_service(
    args: Annotated[GeneratorArgs | None, Depends(try_get_generator_args)],
) -> AlbumService | None:
    """Dependency for GUI to get the album service if it exists."""
    if args is None:
        return None

    try:
        return await get_album_service(args)
    except ValueError:
        return None
