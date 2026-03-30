import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import AsyncIterator, Iterable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, NamedTuple
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.logic.country_colors import build_country_colors
from app.logic.layout import Layout, build_step_layout
from app.logic.layout.media import (
    MEDIA_EXTENSIONS,
    Media,
    normalize_name,
)
from app.logic.spatial.geo import haversine_km
from app.logic.spatial.peaks import correct_peaks
from app.logic.spatial.segments import build_segments
from app.models.album import DEFAULT_BODY_FONT, DEFAULT_FONT, Album
from app.models.polarsteps import Location, Point, PSLocations, PSStep, PSTrip
from app.models.segment import Segment, SegmentKind
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


class TripResults(NamedTuple):
    elevations: list[float]
    weather_by_idx: dict[int, Weather]
    layout_by_idx: dict[int, Layout | None]
    cover_name: str


def segment_timezone(seg_start: float, all_steps: list[PSStep]) -> str:
    """Find the timezone of the step closest to a segment's start time."""
    best = all_steps[0]
    for step in all_steps:
        if step.timestamp <= seg_start:
            best = step
        else:
            break
    return best.timezone_id


ACTIVE_HIKE_DAY_MIN_KM = 2.0


def _merge_date_ranges(
    ranges: list[tuple[date, date]],
) -> list[tuple[date, date]]:
    """Sort and merge overlapping or adjacent date ranges."""
    if not ranges:
        return []
    merged = [sorted(ranges)[0]]
    for start, end in sorted(ranges)[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def multi_day_hike_ranges(
    segments: list[Segment],
) -> list[tuple[date, date]]:
    """Return date ranges for hike segments with significant hiking on ≥2 days.

    For each hike segment, partitions GPS points by calendar day and computes
    the haversine distance traveled per day.  Only days with ≥ ACTIVE_HIKE_DAY_MIN_KM
    count.  Overlapping ranges from adjacent segments are merged.
    """
    ranges: list[tuple[date, date]] = []
    for seg in segments:
        if seg.kind != SegmentKind.hike:
            continue
        tz = ZoneInfo(seg.timezone_id)

        daily_km: dict[date, float] = defaultdict(float)
        pts = seg.points
        for i in range(1, len(pts)):
            day = datetime.fromtimestamp(pts[i].time, tz).date()
            daily_km[day] += haversine_km(
                pts[i - 1].lat, pts[i - 1].lon, pts[i].lat, pts[i].lon
            )

        active_days = sorted(
            d for d, km in daily_km.items() if km >= ACTIVE_HIKE_DAY_MIN_KM
        )
        if len(active_days) >= 2:
            ranges.append((active_days[0], active_days[-1]))

    return _merge_date_ranges(ranges)


def build_segment_objects(
    uid: int,
    aid: str,
    steps: Sequence[Step],
    locations: Iterable[Point],
    all_ps_steps: list[PSStep],
) -> list[Segment]:
    """Build Segment DB objects from GPS locations and step waypoints."""
    return [
        Segment(
            uid=uid,
            aid=aid,
            start_time=seg.points[0].time,
            end_time=seg.points[-1].time,
            kind=seg.kind,
            timezone_id=segment_timezone(seg.points[0].time, all_ps_steps),
            points=seg.points,
        )
        for seg in build_segments(steps, locations)
    ]


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

    merged_media: list[Media] = []
    seen: set[str] = set()
    for layout in layouts:
        if layout:
            for m in layout.media:
                if m.name not in seen:
                    merged_media.append(m)
                    seen.add(m.name)

    steps = [
        build_step(user.id, aid, ps, elev, wthr, layout)
        for ps, elev, wthr, layout in zip(
            trip.all_steps, results.elevations, weathers, layouts, strict=True
        )
    ]
    segments = build_segment_objects(user.id, aid, steps, locations, trip.all_steps)

    album = Album(
        uid=user.id,
        id=aid,
        colors=build_country_colors(
            {s.location.country_code for s in trip.all_steps},
        ),
        excluded_steps=[],
        maps_ranges=multi_day_hike_ranges(segments),
        title=trip.title,
        subtitle=trip.subtitle,
        front_cover_photo=results.cover_name,
        back_cover_photo=results.cover_name,
        media=merged_media,
        font=DEFAULT_FONT,
        body_font=DEFAULT_FONT if user.locale.startswith("he") else DEFAULT_BODY_FONT,
    )
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
) -> tuple[dict[int, Layout | None], str]:
    """Layouts -> flatten (sequential pipeline).

    Runs as one TaskGroup member so flattening starts as soon as
    layouts finish, without waiting for the API calls to complete.
    Video posters and thumbnails are generated lazily on first request.
    Returns (layout_by_idx, cover_name).
    """
    aid = trip_dir.name
    n_steps = len(trip.all_steps)
    layout_by_idx = dict(
        await track_iter(
            "layouts", n_steps, fetch_layouts(user, aid, trip.all_steps), queue
        )
    )

    cover_name, _cover_orientation = await prepare_media(trip_dir, cover_name)

    return layout_by_idx, cover_name


def resolve_international_waters(steps: list[PSStep]) -> None:
    """Replace '00' (international waters) country codes with the previous step's code.

    Polarsteps uses '00' for steps at sea. This assigns them to the last
    visited country and warns when the *next* land step belongs to a
    different country (ambiguous attribution).
    """
    prev_code: str | None = None
    run: list[PSStep] = []

    for step in steps:
        if step.location.country_code == "00":
            if prev_code is not None:
                step.location.country_code = prev_code
                run.append(step)
            continue

        if run and step.location.country_code != prev_code:
            names = ", ".join(s.name for s in run)
            logger.warning(
                "International-water steps [%s] attributed to %s, "
                "but next step '%s' is %s",
                names,
                prev_code.upper(),  # type: ignore[union-attr]
                step.name,
                step.location.country_code.upper(),
            )
        run.clear()
        prev_code = step.location.country_code


def load_trip_data(trip_dir: Path) -> tuple[PSTrip, list[Point]]:
    """Read trip metadata and GPS locations (blocking I/O, run in thread)."""
    trip = PSTrip.from_trip_dir(trip_dir)
    resolve_international_waters(trip.all_steps)
    locations = PSLocations.from_trip_dir(trip_dir).locations
    return trip, locations
