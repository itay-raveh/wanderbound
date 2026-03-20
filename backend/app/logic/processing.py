import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from pathlib import Path
from typing import Annotated, Any, Literal, NamedTuple

from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.core.http import cached_client
from app.logic.country_colors import build_country_colors
from app.logic.layout import Layout, build_step_layout
from app.logic.layout.media import (
    MEDIA_EXTENSIONS,
    Media,
    extract_frame,
    generate_thumbnails,
    normalize_name,
)
from app.logic.spatial.peaks import correct_peaks
from app.logic.spatial.segments import build_segments
from app.models.album import Album
from app.models.polarsteps import Location, Point, PSLocations, PSStep, PSTrip
from app.models.segment import Segment
from app.models.step import Step
from app.models.user import User
from app.models.weather import Weather
from app.services.open_meteo import build_weathers, elevations

logger = logging.getLogger(__name__)

type ProcessingPhase = Literal["elevations", "weather", "layouts", "frames", "thumbs"]
type DbRow = Album | Step | Segment

# Limit concurrent heavy media work (ffmpeg frame extraction, Pillow thumbnails).
# Budget: ~1600 MB total / ~80 MB per ffmpeg process = 20 slots.
_media_sem = asyncio.Semaphore(20)


async def _track_iter[T](
    phase: ProcessingPhase,
    total: int,
    source: AsyncIterator[T],
    queue: asyncio.Queue[PhaseUpdate | None],
) -> list[T]:
    await queue.put(PhaseUpdate(phase=phase, done=0, total=total))
    results: list[T] = []
    async for item in source:
        results.append(item)
        await queue.put(PhaseUpdate(phase=phase, done=len(results), total=total))
    return results


async def _run_phase(
    phase: ProcessingPhase,
    files: list[Path],
    worker: Callable[[Path], Coroutine[Any, Any, None]],
    queue: asyncio.Queue[PhaseUpdate | None],
) -> None:
    if not files:
        return
    total = len(files)
    await queue.put(PhaseUpdate(phase=phase, done=0, total=total))

    async def _safe(p: Path) -> None:
        try:
            await worker(p)
        except (RuntimeError, OSError) as exc:
            logger.warning("%s failed for %s: %s", phase, p.name, exc)

    for done, coro in enumerate(asyncio.as_completed([_safe(p) for p in files]), 1):
        await coro
        await queue.put(PhaseUpdate(phase=phase, done=done, total=total))


_cover_client = cached_client()


async def _download_cover(url: HttpUrl, dest: Path) -> None:
    resp = await _cover_client.get(str(url))
    resp.raise_for_status()
    await asyncio.to_thread(dest.write_bytes, resp.content)


class TripStart(BaseModel):
    type: Literal["trip_start"] = "trip_start"
    trip_index: int


class PhaseUpdate(BaseModel):
    type: Literal["phase"] = "phase"
    phase: ProcessingPhase
    done: int
    total: int


class ErrorData(BaseModel):
    type: Literal["error"] = "error"
    detail: str


ProcessingEvent = Annotated[
    TripStart | PhaseUpdate | ErrorData,
    Field(discriminator="type"),
]


async def _fetch_layouts(
    user: User,
    aid: str,
    steps: list[PSStep],
) -> AsyncIterator[tuple[int, Layout | None]]:
    """Yield (index, layout) as each completes (concurrent, unordered)."""

    async def _one(
        idx: int,
        step: PSStep,
    ) -> tuple[int, Layout | None]:
        return idx, await build_step_layout(user, aid, step)

    for coro in asyncio.as_completed([_one(i, s) for i, s in enumerate(steps)]):
        yield await coro


def _flatten_media(album_dir: Path) -> None:
    dirs: list[Path] = []
    for entry in album_dir.rglob("*"):
        if entry.is_file() and entry.suffix.lower() in MEDIA_EXTENSIONS:
            entry.rename(album_dir / normalize_name(entry.name))
        elif entry.is_dir():
            dirs.append(entry)
    for d in sorted(dirs, reverse=True):
        with contextlib.suppress(OSError):
            d.rmdir()


class _TripResults(NamedTuple):
    elevations: list[float]
    weather_by_idx: dict[int, Weather]
    layout_by_idx: dict[int, Layout | None]
    cover_name: str
    cover_orientation: str


def _build_trip_objects(
    user: User,
    aid: str,
    trip: PSTrip,
    locations: list[Point],
    results: _TripResults,
) -> list[DbRow]:
    n = len(trip.all_steps)
    weathers = [results.weather_by_idx[i] for i in range(n)]
    layouts = [results.layout_by_idx[i] for i in range(n)]

    merged_orientations: dict[str, str] = {
        results.cover_name: results.cover_orientation,
    }
    for layout in layouts:
        if layout:
            merged_orientations.update(layout.orientations)

    first_date = trip.all_steps[0].datetime.date()
    last_date = trip.all_steps[-1].datetime.date()
    album = Album(
        uid=user.id,
        id=aid,
        colors=build_country_colors(
            {s.location.country_code for s in trip.all_steps},
        ),
        steps_ranges=[(first_date, last_date)],
        title=trip.title,
        subtitle=trip.subtitle,
        front_cover_photo=results.cover_name,
        back_cover_photo=results.cover_name,
        orientations=merged_orientations,
    )
    steps = [
        Step(
            uid=user.id,
            aid=aid,
            idx=idx,
            name=ps.name,
            description=ps.description,
            timestamp=ps.timestamp,
            timezone_id=ps.timezone_id,
            location=ps.location,
            elevation=elev,
            weather=wthr,
            cover=layout.cover if layout else None,
            pages=layout.pages if layout else [],
            unused=[],
        )
        for idx, (ps, elev, wthr, layout) in enumerate(
            zip(trip.all_steps, results.elevations, weathers, layouts, strict=True)
        )
    ]
    segments = [
        Segment(
            uid=user.id,
            aid=aid,
            start_time=seg.points[0].time,
            end_time=seg.points[-1].time,
            kind=seg.kind,
            points=seg.points,
        )
        for seg in build_segments(steps, locations)
    ]
    return [album, *steps, *segments]


async def _extract_one(p: Path) -> None:
    async with _media_sem:
        await extract_frame(p)


async def _thumb_one(p: Path) -> None:
    async with _media_sem:
        await generate_thumbnails(p)


async def _run_elevations(
    locs: list[Location],
    n_steps: int,
    queue: asyncio.Queue[PhaseUpdate | None],
) -> list[float]:
    raw = await _track_iter("elevations", n_steps, elevations(locs), queue)
    return list(await correct_peaks(locs, raw))


async def _run_weather(
    steps: list[PSStep],
    n_steps: int,
    queue: asyncio.Queue[PhaseUpdate | None],
) -> dict[int, Weather]:
    return dict(await _track_iter("weather", n_steps, build_weathers(steps), queue))


async def _media_pipeline(
    user: User,
    trip: PSTrip,
    trip_dir: Path,
    cover_name: str,
    queue: asyncio.Queue[PhaseUpdate | None],
) -> tuple[dict[int, Layout | None], str]:
    """Layouts → flatten → cover → frames → thumbs (sequential pipeline).

    Runs as one TaskGroup member so frame extraction starts as soon as
    layouts finish, without waiting for the API calls to complete.
    Returns (layout_by_idx, cover_orientation).
    """
    aid = trip_dir.name
    n_steps = len(trip.all_steps)
    layout_by_idx = dict(
        await _track_iter(
            "layouts", n_steps, _fetch_layouts(user, aid, trip.all_steps), queue
        )
    )

    await asyncio.to_thread(_flatten_media, trip_dir)

    cover_dest = trip_dir / cover_name
    if not cover_dest.exists():
        await _download_cover(trip.cover_photo_path, cover_dest)

    try:
        cover_photo = await asyncio.to_thread(Media.load, cover_dest)
        cover_orientation = cover_photo.orientation
    except OSError, ValueError:
        logger.warning(
            "Could not determine cover orientation for %s, defaulting to 'l'",
            cover_name,
        )
        cover_orientation = "l"

    all_files = list(trip_dir.iterdir())  # noqa: ASYNC240
    video_paths = [p for p in all_files if p.suffix.lower() == ".mp4"]
    existing_jpgs = [p for p in all_files if p.suffix.lower() == ".jpg"]

    await _run_phase("frames", video_paths, _extract_one, queue)

    poster_jpgs = {p.with_suffix(".jpg") for p in video_paths}
    jpg_files = list({*existing_jpgs, *(p for p in poster_jpgs if p.is_file())})

    await _run_phase("thumbs", jpg_files, _thumb_one, queue)

    return layout_by_idx, cover_orientation


async def _process_trip(
    user: User,
    trip_dir: Path,
    db_out: list[DbRow],
) -> AsyncIterator[PhaseUpdate]:
    aid = trip_dir.name
    trip = PSTrip.from_trip_dir(trip_dir)
    locations = PSLocations.from_trip_dir(trip_dir).locations
    logger.info("Processing '%s' with %d steps...", trip.title, trip.step_count)
    locs = [s.location for s in trip.all_steps]

    queue: asyncio.Queue[PhaseUpdate | None] = asyncio.Queue()
    cover_name = normalize_name(Path(trip.cover_photo_path.path or "").name)
    n = len(trip.all_steps)

    async def _phases() -> _TripResults:
        try:
            async with asyncio.TaskGroup() as tg:
                elev_task = tg.create_task(_run_elevations(locs, n, queue))
                weather_task = tg.create_task(_run_weather(trip.all_steps, n, queue))
                media_task = tg.create_task(
                    _media_pipeline(user, trip, trip_dir, cover_name, queue)
                )
        finally:
            await queue.put(None)
        layout_by_idx, cover_orientation = media_task.result()
        return _TripResults(
            elevations=elev_task.result(),
            weather_by_idx=weather_task.result(),
            layout_by_idx=layout_by_idx,
            cover_name=cover_name,
            cover_orientation=cover_orientation,
        )

    runner = asyncio.create_task(_phases())

    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        if not runner.done():
            runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await runner

    # Re-raise phase errors (only reached on normal sentinel break,
    # not on generator close where the finally terminates the generator).
    results = await runner
    db_out.extend(_build_trip_objects(user, aid, trip, locations, results))


async def run_processing(user: User) -> AsyncIterator[ProcessingEvent]:
    trip_dirs = sorted(user.trips_folder.iterdir())
    all_objects: list[DbRow] = []
    try:
        for trip_idx, trip_dir in enumerate(trip_dirs):
            yield TripStart(trip_index=trip_idx)
            async for event in _process_trip(user, trip_dir, all_objects):
                yield event
    except Exception:
        logger.exception("Processing failed for user %d", user.id)
        yield ErrorData(
            detail="Processing failed. Please try again later.",
        )
        return

    try:
        async with AsyncSession(engine) as session:
            session.add_all(all_objects)
            await session.commit()
        logger.info(
            "Saved %d objects to database for user %d", len(all_objects), user.id
        )
    except SQLAlchemyError:
        logger.exception("DB save failed for user %d", user.id)
        yield ErrorData(detail="Processing failed. Please try again later.")
