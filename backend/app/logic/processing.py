import asyncio
import contextlib
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.core.logging import config_logger
from app.logic.country_colors import build_country_colors
from app.logic.layout import build_step_layout
from app.logic.layout.media import MEDIA_EXTENSIONS, MediaName, normalize_name
from app.logic.spatial.elevation import elevations
from app.logic.spatial.peaks import correct_peaks
from app.logic.spatial.segments import build_segments
from app.logic.weather import Weather, build_weathers
from app.models.album import Album
from app.models.polarsteps import PSLocations, PSStep, PSTrip
from app.models.segment import Segment
from app.models.step import Step
from app.models.user import User

logger = config_logger(__name__)

type ProcessingPhase = Literal["elevations", "weather", "layouts"]
type DbRow = Album | Step | Segment


class TripStart(BaseModel):
    type: Literal["trip_start"] = "trip_start"
    trip_index: int


class PhaseUpdate(BaseModel):
    type: Literal["phase"] = "phase"
    phase: ProcessingPhase
    done: int


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
) -> AsyncIterator[tuple[int, tuple[MediaName, list[list[MediaName]]]]]:
    """Yield (index, layout) as each completes (concurrent, unordered)."""
    sem = asyncio.Semaphore(10)

    async def _one(
        idx: int,
        step: PSStep,
    ) -> tuple[int, tuple[MediaName, list[list[MediaName]]]]:
        async with sem:
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
    trip: PSTrip,
    trip_dir: Path,
    elevs: Sequence[float],
    weathers: Sequence[Weather],
    layouts: Sequence[tuple[MediaName, list[list[MediaName]]]],
) -> list[DbRow]:
    aid = trip_dir.name
    album = Album(
        uid=user.id,
        id=aid,
        colors=build_country_colors(
            {s.location.country_code for s in trip.all_steps},
        ),
        steps_ranges=f"0-{len(trip.all_steps) - 1}",
        title=trip.title,
        subtitle=trip.subtitle,
        front_cover_photo=str(trip.cover_photo_path),
        back_cover_photo=str(trip.cover_photo_path),
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
            cover=cover,
            pages=pages,
            unused=[],
        )
        for idx, (ps, elev, wthr, (cover, pages)) in enumerate(
            zip(trip.all_steps, elevs, weathers, layouts, strict=True)
        )
    ]
    locations = PSLocations.from_trip_dir(trip_dir).locations
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


async def _process_trip(
    user: User,
    trip_dir: Path,
    db_out: list[DbRow],
) -> AsyncIterator[PhaseUpdate]:
    trip = PSTrip.from_trip_dir(trip_dir)
    logger.info("Processing '%s' with %d steps...", trip.title, trip.step_count)
    locs = [s.location for s in trip.all_steps]

    # Phases run sequentially so the SSE stream can report per-item progress.

    raw: list[float] = []
    async for elev in elevations(locs):
        raw.append(elev)
        yield PhaseUpdate(phase="elevations", done=len(raw))
    elevs = await correct_peaks(locs, raw)

    weathers: list[Weather] = []
    async for weather in build_weathers(trip.all_steps):
        weathers.append(weather)
        yield PhaseUpdate(phase="weather", done=len(weathers))

    layout_by_idx: dict[int, tuple[MediaName, list[list[MediaName]]]] = {}
    async for idx, layout in _fetch_layouts(user, trip_dir.name, trip.all_steps):
        layout_by_idx[idx] = layout
        yield PhaseUpdate(phase="layouts", done=len(layout_by_idx))
    layouts = [layout_by_idx[i] for i in range(len(trip.all_steps))]

    await asyncio.to_thread(_flatten_media, trip_dir)

    db_out.extend(
        _build_trip_objects(user, trip, trip_dir, elevs, weathers, layouts),
    )


async def process_stream(user: User) -> AsyncIterator[ProcessingEvent]:
    trip_dirs = sorted(user.trips_folder.iterdir())
    all_objects: list[DbRow] = []
    try:
        for trip_idx, trip_dir in enumerate(trip_dirs):
            yield TripStart(trip_index=trip_idx)
            async for event in _process_trip(user, trip_dir, all_objects):
                yield event
    except Exception:
        logger.exception("Processing failed")
        yield ErrorData(
            detail="Processing failed. Please try again later.",
        )
        return

    try:
        album_ids = [obj.id for obj in all_objects if isinstance(obj, Album)]
        user.album_ids = album_ids
        async with AsyncSession(engine) as session:
            session.add_all(all_objects)
            await session.merge(user)
            await session.commit()
    except Exception:
        logger.exception("DB save failed")
        yield ErrorData(detail="Processing failed. Please try again later.")
