import asyncio
import contextlib
import logging
import shutil
from collections import defaultdict
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any, Literal, NamedTuple

from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.logic.country_colors import build_country_colors
from app.logic.layout import Layout, build_step_layout
from app.logic.layout.media import (
    MEDIA_EXTENSIONS,
    Media,
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

type ProcessingPhase = Literal["elevations", "weather", "layouts"]
type DbRow = Album | Step | Segment


async def track_iter[T](
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


ProcessingEvent = Annotated[
    TripStart | PhaseUpdate | ErrorData,
    Field(discriminator="type"),
]


async def fetch_layouts(
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


def flatten_media(album_dir: Path) -> None:
    dirs: list[Path] = []
    for entry in album_dir.rglob("*"):
        if entry.is_file() and entry.suffix.lower() in MEDIA_EXTENSIONS:
            entry.rename(album_dir / normalize_name(entry.name))
        elif entry.is_dir():
            dirs.append(entry)
    for d in sorted(dirs, reverse=True):
        with contextlib.suppress(OSError):
            d.rmdir()


_POLARSTEPS_METADATA = {"trip.json", "locations.json"}


def _cleanup_metadata(user_folder: Path, trip_dirs: list[Path]) -> None:
    """Free disk and avoid leaking raw location history after ingestion."""
    for td in trip_dirs:
        for name in _POLARSTEPS_METADATA:
            (td / name).unlink(missing_ok=True)

    shutil.rmtree(user_folder / "user", ignore_errors=True)

    logger.debug("Cleaned up Polarsteps metadata for %s", user_folder.name)


class TripResults(NamedTuple):
    elevations: list[float]
    weather_by_idx: dict[int, Weather]
    layout_by_idx: dict[int, Layout | None]
    cover_name: str
    cover_orientation: str


def build_trip_objects(
    user: User,
    aid: str,
    trip: PSTrip,
    locations: list[Point],
    results: TripResults,
) -> list[DbRow]:
    n = len(trip.all_steps)
    weathers = [results.weather_by_idx[i] for i in range(n)]
    layouts = [results.layout_by_idx[i] for i in range(n)]

    merged_media: dict[str, str] = {
        results.cover_name: results.cover_orientation,
    }
    for layout in layouts:
        if layout:
            merged_media.update(layout.orientations)

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
        media=merged_media,
    )
    steps = [
        build_step(user.id, aid, ps, elev, wthr, layout)
        for ps, elev, wthr, layout in zip(
            trip.all_steps, results.elevations, weathers, layouts, strict=True
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


async def run_elevations(
    locs: list[Location],
    n_steps: int,
    queue: asyncio.Queue[PhaseUpdate | None],
) -> list[float]:
    raw = await track_iter("elevations", n_steps, elevations(locs), queue)
    return list(await correct_peaks(locs, raw))


async def run_weather(
    steps: list[PSStep],
    n_steps: int,
    queue: asyncio.Queue[PhaseUpdate | None],
) -> dict[int, Weather]:
    return dict(await track_iter("weather", n_steps, build_weathers(steps), queue))


def _pick_landscape_cover(trip_dir: Path) -> tuple[str, str]:
    """Pick a random landscape photo as cover fallback. Returns (name, orientation)."""
    for path in trip_dir.iterdir():
        if path.suffix.lower() != ".jpg":
            continue
        try:
            m = Media.load(path)
            if m.orientation == "l":
                return m.name, "l"
        except OSError, ValueError:
            continue
    # No landscape found - just use the first jpg
    for path in trip_dir.iterdir():
        if path.suffix.lower() == ".jpg":
            return normalize_name(path.name), "l"
    return "", "l"


async def prepare_media(
    trip_dir: Path,
    cover_name: str,
) -> tuple[str, str]:
    """Flatten media and detect cover photo.

    Shared between full processing and reconciliation.
    Returns (cover_name, cover_orientation). If the cover file from the
    Polarsteps export isn't found locally, picks a landscape photo instead.
    Video posters and thumbnails are generated lazily on first request.
    """
    await asyncio.to_thread(flatten_media, trip_dir)

    cover_dest = trip_dir / cover_name
    if cover_dest.exists():
        try:
            cover_photo = await asyncio.to_thread(Media.load, cover_dest)
            cover_orientation = cover_photo.orientation
        except OSError, ValueError:
            cover_orientation = "l"
    else:
        cover_name, cover_orientation = await asyncio.to_thread(
            _pick_landscape_cover, trip_dir
        )

    return cover_name, cover_orientation


async def drain_queue(
    task: asyncio.Task[Any],
    queue: asyncio.Queue[PhaseUpdate | None],
) -> AsyncIterator[PhaseUpdate]:
    """Yield phase updates from queue until sentinel, cancelling task on early close."""
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def build_step(  # noqa: PLR0913
    uid: int,
    aid: str,
    ps: PSStep,
    elev: float,
    wthr: Weather,
    layout: Layout | None,
) -> Step:
    return Step(
        uid=uid,
        aid=aid,
        id=ps.id,
        name=ps.name,
        description=ps.description,
        timestamp=ps.timestamp,
        timezone_id=ps.timezone_id,
        location=ps.location,
        elevation=round(elev),
        weather=wthr,
        cover=layout.cover if layout else None,
        pages=layout.pages if layout else [],
        unused=[],
    )


def cover_name_from_trip(trip: PSTrip) -> str:
    return normalize_name(Path(trip.cover_photo_path.path or "").name)


async def _media_pipeline(
    user: User,
    trip: PSTrip,
    trip_dir: Path,
    cover_name: str,
    queue: asyncio.Queue[PhaseUpdate | None],
) -> tuple[dict[int, Layout | None], str, str]:
    """Layouts -> flatten (sequential pipeline).

    Runs as one TaskGroup member so flattening starts as soon as
    layouts finish, without waiting for the API calls to complete.
    Video posters and thumbnails are generated lazily on first request.
    Returns (layout_by_idx, cover_name, cover_orientation).
    """
    aid = trip_dir.name
    n_steps = len(trip.all_steps)
    layout_by_idx = dict(
        await track_iter(
            "layouts", n_steps, fetch_layouts(user, aid, trip.all_steps), queue
        )
    )

    cover_name, cover_orientation = await prepare_media(trip_dir, cover_name)

    return layout_by_idx, cover_name, cover_orientation


def load_trip_data(trip_dir: Path) -> tuple[PSTrip, list[Point]]:
    """Read trip metadata and GPS locations (blocking I/O, run in thread)."""
    trip = PSTrip.from_trip_dir(trip_dir)
    locations = PSLocations.from_trip_dir(trip_dir).locations
    return trip, locations


async def _process_trip(
    user: User,
    trip_dir: Path,
    db_out: list[DbRow],
) -> AsyncIterator[PhaseUpdate]:
    aid = trip_dir.name
    trip, locations = await asyncio.to_thread(load_trip_data, trip_dir)
    logger.info("Processing '%s' with %d steps...", trip.title, trip.step_count)
    locs = [s.location for s in trip.all_steps]

    queue: asyncio.Queue[PhaseUpdate | None] = asyncio.Queue()
    cover_name = cover_name_from_trip(trip)
    n = len(trip.all_steps)

    async def _phases() -> TripResults:
        try:
            async with asyncio.TaskGroup() as tg:
                elev_task = tg.create_task(run_elevations(locs, n, queue))
                weather_task = tg.create_task(run_weather(trip.all_steps, n, queue))
                media_task = tg.create_task(
                    _media_pipeline(user, trip, trip_dir, cover_name, queue)
                )
        finally:
            await queue.put(None)
        layout_by_idx, final_cover_name, cover_orientation = media_task.result()
        return TripResults(
            elevations=elev_task.result(),
            weather_by_idx=weather_task.result(),
            layout_by_idx=layout_by_idx,
            cover_name=final_cover_name,
            cover_orientation=cover_orientation,
        )

    runner = asyncio.create_task(_phases())
    async for event in drain_queue(runner, queue):
        yield event

    results = await runner
    objects = await asyncio.to_thread(
        build_trip_objects, user, aid, trip, locations, results
    )
    db_out.extend(objects)


async def _load_existing(
    user: User,
) -> tuple[dict[str, Album], dict[str, list[Step]]]:
    """Load existing albums and steps for reconciliation.

    Returns empty dicts for new users (no albums yet).
    """
    if not user.album_ids:
        return {}, {}

    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        albums = {
            a.id: a
            for a in (
                await session.exec(select(Album).where(Album.uid == user.id))
            ).all()
        }

        steps_by_aid: dict[str, list[Step]] = defaultdict(list)
        for s in (await session.exec(select(Step).where(Step.uid == user.id))).all():
            steps_by_aid[s.aid].append(s)

    return albums, dict(steps_by_aid)


async def _save_new(
    uid: int,
    objects: list[DbRow],
) -> None:
    async with AsyncSession(get_engine()) as session:
        session.add_all(objects)
        await session.commit()
    logger.info("Saved %d objects to database for user %d", len(objects), uid)


async def _save_reupload(
    uid: int,
    objects: list[DbRow],
    reconciled_aids: set[str],
    existing_albums: dict[str, Album],
    trip_dirs: list[Path],
) -> None:
    async with AsyncSession(get_engine()) as session:
        if reconciled_aids:
            await session.exec(
                delete(Step)
                .where(Step.uid == uid)  # type: ignore[arg-type]
                .where(Step.aid.in_(reconciled_aids))  # type: ignore[union-attr]
            )

        current_aids = {d.name for d in trip_dirs}
        orphan_aids = set(existing_albums) - current_aids
        if orphan_aids:
            await session.exec(
                delete(Album)
                .where(Album.uid == uid)  # type: ignore[arg-type]
                .where(Album.id.in_(orphan_aids))  # type: ignore[union-attr]
            )
        await session.flush()

        for obj in objects:
            await session.merge(obj)
        await session.commit()
    logger.info("Saved %d objects to database for user %d", len(objects), uid)


async def run_processing(user: User) -> AsyncIterator[ProcessingEvent]:
    from app.logic.reconcile import reconcile_trip  # noqa: PLC0415

    trip_dirs = sorted(user.trips_folder.iterdir())
    existing_albums, existing_steps = await _load_existing(user)

    all_objects: list[DbRow] = []
    reconciled_aids: set[str] = set()
    try:
        for trip_idx, trip_dir in enumerate(trip_dirs):
            aid = trip_dir.name
            yield TripStart(trip_index=trip_idx)

            if aid in existing_albums:
                async for event in reconcile_trip(
                    user,
                    trip_dir,
                    existing_albums[aid],
                    existing_steps.get(aid, []),
                    all_objects,
                ):
                    yield event
                reconciled_aids.add(aid)
            else:
                async for event in _process_trip(user, trip_dir, all_objects):
                    yield event
    except Exception:
        logger.exception("Processing failed for user %d", user.id)
        yield ErrorData()
        return

    try:
        if existing_albums:
            await _save_reupload(
                user.id, all_objects, reconciled_aids, existing_albums, trip_dirs
            )
        else:
            await _save_new(user.id, all_objects)
    except SQLAlchemyError:
        logger.exception("DB save failed for user %d", user.id)
        yield ErrorData()
        return

    await asyncio.to_thread(_cleanup_metadata, user.folder, trip_dirs)
