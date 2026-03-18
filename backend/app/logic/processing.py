import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable, Coroutine, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal

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
from app.models.polarsteps import Point, PSLocations, PSStep, PSTrip
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
    for done, coro in enumerate(asyncio.as_completed([worker(p) for p in files]), 1):
        try:
            await coro
        except (RuntimeError, OSError) as exc:
            logger.warning("%s failed: %s", phase, exc)
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


def _build_trip_objects(  # noqa: PLR0913
    user: User,
    aid: str,
    trip: PSTrip,
    locations: list[Point],
    elevs: Sequence[float],
    weathers: Sequence[Weather],
    layouts: Sequence[Layout | None],
    cover_name: str,
    cover_orientation: str,
) -> list[DbRow]:
    merged_orientations: dict[str, str] = {cover_name: cover_orientation}
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
        maps_ranges=[(first_date, last_date)],
        title=trip.title,
        subtitle=trip.subtitle,
        front_cover_photo=cover_name,
        back_cover_photo=cover_name,
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
            zip(trip.all_steps, elevs, weathers, layouts, strict=True)
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


async def _process_trip(  # noqa: C901, PLR0915
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

    # Extract cover filename from the URL path (already {uuid}_{uuid}.jpg).
    cover_url_path = trip.cover_photo_path.path or ""
    cover_name = normalize_name(Path(cover_url_path).name)

    n_steps = len(trip.all_steps)

    async def _run_elevations() -> list[float]:
        raw = await _track_iter("elevations", n_steps, elevations(locs), queue)
        return list(await correct_peaks(locs, raw))

    async def _run_weather() -> dict[int, Weather]:
        return dict(
            await _track_iter("weather", n_steps, build_weathers(trip.all_steps), queue)
        )

    async def _run_media_pipeline() -> tuple[dict[int, Layout | None], str]:
        """Layouts → flatten → cover → frames → thumbs (sequential pipeline).

        Runs as one TaskGroup member so frame extraction starts as soon as
        layouts finish, without waiting for the API calls to complete.
        Returns (layout_by_idx, cover_orientation).
        """
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
        except Exception:  # noqa: BLE001
            logger.warning(
                "Could not determine cover orientation for %s, defaulting to 'l'",
                cover_name,
            )
            cover_orientation = "l"

        all_files = list(trip_dir.iterdir())  # noqa: ASYNC240
        video_paths = [p for p in all_files if p.suffix.lower() == ".mp4"]
        existing_jpgs = [p for p in all_files if p.suffix.lower() == ".jpg"]

        async def _extract_one(p: Path) -> None:
            async with _media_sem:
                await extract_frame(p)

        await _run_phase("frames", video_paths, _extract_one, queue)

        poster_jpgs = {p.with_suffix(".jpg") for p in video_paths}
        jpg_files = list({*existing_jpgs, *(p for p in poster_jpgs if p.is_file())})

        async def _thumb_one(p: Path) -> None:
            async with _media_sem:
                await generate_thumbnails(p)

        await _run_phase("thumbs", jpg_files, _thumb_one, queue)

        return layout_by_idx, cover_orientation

    type _TripResults = tuple[
        list[float], dict[int, Weather], tuple[dict[int, Layout | None], str]
    ]

    async def _run_all() -> _TripResults:
        try:
            async with asyncio.TaskGroup() as tg:
                elev_task = tg.create_task(_run_elevations())
                weather_task = tg.create_task(_run_weather())
                media_task = tg.create_task(_run_media_pipeline())
        finally:
            await queue.put(None)
        return elev_task.result(), weather_task.result(), media_task.result()

    runner = asyncio.create_task(_run_all())

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
    elevs_corrected, weather_by_idx, (layout_by_idx, cover_orientation) = await runner

    weathers = [weather_by_idx[i] for i in range(len(trip.all_steps))]
    layouts = [layout_by_idx[i] for i in range(len(trip.all_steps))]

    db_out.extend(
        _build_trip_objects(
            user,
            aid,
            trip,
            locations,
            elevs_corrected,
            weathers,
            layouts,
            cover_name,
            cover_orientation,
        ),
    )


async def _run_processing(user: User) -> AsyncIterator[ProcessingEvent]:
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


_SESSION_TTL = 300  # seconds before a completed session is evicted


def _evict_session(uid: int, session: ProcessingSession) -> None:
    """Remove a completed session if it hasn't been replaced."""
    if _sessions.get(uid) is session:
        del _sessions[uid]


class ProcessingSession:
    """Runs processing in a background task; clients subscribe to events."""

    def __init__(self, user: User) -> None:
        self._events: list[ProcessingEvent] = []
        self._done = False
        self._notify = asyncio.Event()
        self._uid = user.id
        self._task = asyncio.create_task(self._run(user))

    async def _run(self, user: User) -> None:
        try:
            async for event in _run_processing(user):
                self._events.append(event)
                self._notify.set()
        finally:
            self._done = True
            self._notify.set()
            # Schedule cleanup so abandoned sessions don't leak memory.
            # Delay gives reconnecting clients time to attach.
            asyncio.get_running_loop().call_later(
                _SESSION_TTL,
                _evict_session,
                self._uid,
                self,
            )

    @property
    def is_done(self) -> bool:
        return self._done

    async def subscribe(self) -> AsyncIterator[ProcessingEvent]:
        """Yield all events (past and future) until processing completes."""
        idx = 0
        while True:
            while idx < len(self._events):
                yield self._events[idx]
                idx += 1
            if self._done:
                break
            self._notify.clear()
            # Re-check after clear to avoid race with producer
            if idx < len(self._events) or self._done:
                continue
            await self._notify.wait()


_sessions: dict[int, ProcessingSession] = {}


async def process_stream(user: User) -> AsyncIterator[ProcessingEvent]:
    """Start or reconnect to a user's processing session."""
    session = _sessions.get(user.id)

    if session is not None:
        logger.info(
            "User %d reconnecting to %s processing session",
            user.id,
            "completed" if session.is_done else "active",
        )
        async for event in session.subscribe():
            yield event
        return

    session = ProcessingSession(user)
    _sessions[user.id] = session

    async for event in session.subscribe():
        yield event
