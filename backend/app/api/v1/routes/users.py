import asyncio
import contextlib
import re
import shutil
from collections.abc import AsyncIterable, Awaitable, Callable
from pathlib import Path
from typing import Annotated, BinaryIO, Literal
from zipfile import BadZipFile

from fastapi import (
    APIRouter,
    Cookie,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.sse import EventSourceResponse
from pydantic import UUID4, BaseModel, Field
from safezip import SafezipError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.logging import config_logger
from app.logic.country_colors import CountryCode, build_country_colors
from app.logic.layout import build_step_layout
from app.logic.spatial.elevation import elevations
from app.logic.spatial.peaks import correct_peaks
from app.logic.spatial.segments import build_segments
from app.logic.weather import build_weathers
from app.models.db import Album, Segment, Step, User, engine
from app.models.trips import Locations, PSStep, Trip

from ..deps import USER_COOKIE, SessionDep, UserDep

logger = config_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# SSE event models (included in OpenAPI via the discriminated union)
# ---------------------------------------------------------------------------

type ProcessingPhase = Literal["elevations", "weather", "layouts", "segments", "saving"]


class ProgressData(BaseModel):
    type: Literal["progress"] = "progress"
    trip_index: int
    total_trips: int
    trip_title: str
    phase: ProcessingPhase
    step: int
    total: int


class DoneData(BaseModel):
    type: Literal["done"] = "done"


class ErrorData(BaseModel):
    type: Literal["error"] = "error"
    detail: str


ProcessingEvent = Annotated[
    ProgressData | DoneData | ErrorData,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Upload response models
# ---------------------------------------------------------------------------


class TripMeta(BaseModel):
    id: str
    title: str
    step_count: int
    country_codes: list[CountryCode]


class UserCreated(BaseModel):
    user: User
    trips: list[TripMeta]


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------

_UPLOADS_DIR = settings.USERS_FOLDER / "_uploads"


async def _persist_user(file: BinaryIO, response: Response) -> UserCreated:
    """Extract ZIP, persist User row, set cookie, return trip metadata."""
    try:
        user = await asyncio.to_thread(User.from_zip_upload, file)
    except (BadZipFile, SafezipError, OSError) as e:
        logger.exception("Bad ZIP")
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Bad ZIP"
        ) from e

    async with AsyncSession(engine) as session:
        existing = await session.get(User, user.id)
        if existing:
            await session.delete(existing)
            await session.flush()
        session.add(user)
        await session.commit()
        await session.refresh(user)

    response.set_cookie(USER_COOKIE, str(user.id))

    trips: list[TripMeta] = []
    for trip_dir in sorted(user.trips_folder.iterdir()):
        trip = Trip.from_trip_dir(trip_dir)
        trips.append(
            TripMeta(
                id=trip_dir.name,
                title=trip.title,
                step_count=trip.step_count,
                country_codes=list({s.location.country_code for s in trip.all_steps}),
            )
        )

    return UserCreated(user=user, trips=trips)


# ---------------------------------------------------------------------------
# Upload endpoints
# ---------------------------------------------------------------------------


@router.post("")
async def create_user(file: UploadFile, response: Response) -> UserCreated:
    logger.info(
        "Extracting '%s' (%d MB)",
        file.filename,
        (file.size or 0) / 1024 // 1024,
    )
    return await _persist_user(file.file, response)


@router.put("/upload/{upload_id}")
async def upload_chunk(
    upload_id: UUID4,
    request: Request,
    response: Response,
    content_range: Annotated[str, Header()],
) -> UserCreated | None:
    """Receive a file chunk. Returns UserCreated on the final chunk."""
    match = re.match(r"bytes (\d+)-(\d+)/(\d+)", content_range)
    if not match:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Content-Range")
    start, end, total = int(match[1]), int(match[2]), int(match[3])

    upload_dir = _UPLOADS_DIR / str(upload_id)
    upload_path = upload_dir / "data.zip"
    body = await request.body()

    def _write() -> None:
        upload_dir.mkdir(parents=True, exist_ok=True)
        mode = "wb" if start == 0 else "r+b"
        with upload_path.open(mode) as f:
            if start > 0:
                f.seek(start)
            f.write(body)

    await asyncio.to_thread(_write)

    if end + 1 < total:
        response.status_code = status.HTTP_202_ACCEPTED
        return None

    # Last chunk — process the assembled file
    logger.info(
        "Chunked upload %s complete (%d MB)",
        upload_id,
        total // 1024 // 1024,
    )
    try:
        with upload_path.open("rb") as f:
            return await _persist_user(f, response)
    finally:
        await asyncio.to_thread(shutil.rmtree, upload_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# SSE processing endpoint
# ---------------------------------------------------------------------------


async def _fetch_layouts(
    user: User,
    aid: str,
    steps: list[PSStep],
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> list[tuple[Path, list[list[Path]]]]:
    sem = asyncio.Semaphore(10)
    total = len(steps)
    completed = 0

    async def _one(step: PSStep) -> tuple[Path, list[list[Path]]]:
        nonlocal completed
        async with sem:
            result = await build_step_layout(user, aid, step)
        completed += 1
        if on_progress:
            await on_progress(completed, total)
        return result

    return list(await asyncio.gather(*(_one(s) for s in steps)))


async def _process_trip(
    user: User,
    trip_dir: Path,
    trip_idx: int,
    total_trips: int,
    queue: asyncio.Queue[ProcessingEvent | None],
) -> list[Album | Step | Segment]:
    """Process a single trip, returning DB objects to persist."""
    trip = Trip.from_trip_dir(trip_dir)
    trip_title = trip.title
    logger.info("Processing '%s' with %d steps...", trip_title, trip.step_count)

    async def progress(phase: ProcessingPhase, step: int, total: int) -> None:
        await queue.put(
            ProgressData(
                trip_index=trip_idx,
                total_trips=total_trips,
                trip_title=trip_title,
                phase=phase,
                step=step,
                total=total,
            )
        )

    # -- Elevations + Weather (concurrent) --
    locs = [s.location for s in trip.all_steps]
    raw, weathers = await asyncio.gather(
        elevations(
            locs,
            on_progress=lambda s, t: progress("elevations", s, t),
        ),
        build_weathers(
            trip.all_steps,
            on_progress=lambda s, t: progress("weather", s, t),
        ),
    )
    elevs = await correct_peaks(locs, raw)
    logger.info("Fetched elevations and weather")

    # -- Layouts --
    colors = build_country_colors({s.location.country_code for s in trip.all_steps})
    album = Album(
        uid=user.id,
        id=trip_dir.name,
        colors=colors,
        steps_ranges=f"0-{len(trip.all_steps) - 1}",
        title=trip.title,
        subtitle=trip.subtitle,
        front_cover_photo=str(trip.cover_photo_path),
        back_cover_photo=str(trip.cover_photo_path),
    )
    layouts = await _fetch_layouts(
        user,
        album.id,
        trip.all_steps,
        on_progress=lambda s, t: progress("layouts", s, t),
    )
    logger.info("Built layouts")

    # -- Build DB objects --
    db_objects: list[Album | Step | Segment] = [album]
    db_steps: list[Step] = []
    for idx, (step, elevation, weather, (cover, pages)) in enumerate(
        zip(trip.all_steps, elevs, weathers, layouts, strict=True)
    ):
        db_step = Step(
            uid=user.id,
            aid=album.id,
            idx=idx,
            name=step.name,
            description=step.description,
            timestamp=step.timestamp,
            timezone_id=step.timezone_id,
            location=step.location,
            elevation=elevation,
            weather=weather,
            cover=cover,
            pages=pages,
            unused=[],
        )
        db_steps.append(db_step)
        db_objects.append(db_step)

    # -- Segments --
    await progress("segments", 0, 1)
    locations = Locations.from_trip_dir(trip_dir).locations
    segments = list(build_segments(db_steps, locations))
    db_objects.extend(
        Segment(
            uid=user.id,
            aid=album.id,
            start_time=seg.points[0].time,
            end_time=seg.points[-1].time,
            kind=seg.kind,
            points=seg.points,
        )
        for seg in segments
    )
    await progress("segments", 1, 1)
    logger.info("Built segments")

    return db_objects


async def _process_stream(
    user: User,
) -> AsyncIterable[ProcessingEvent]:
    """Process all trips and yield SSE events."""
    queue: asyncio.Queue[ProcessingEvent | None] = asyncio.Queue()

    async def run() -> None:
        try:
            trip_dirs = sorted(user.trips_folder.iterdir())
            total_trips = len(trip_dirs)
            all_db_objects: list[Album | Step | Segment] = []

            for trip_idx, trip_dir in enumerate(trip_dirs):
                objects = await _process_trip(
                    user,
                    trip_dir,
                    trip_idx,
                    total_trips,
                    queue,
                )
                all_db_objects.extend(objects)

            # -- Save to DB --
            save_progress = ProgressData(
                trip_index=total_trips - 1,
                total_trips=total_trips,
                trip_title="",
                phase="saving",
                step=0,
                total=1,
            )
            await queue.put(save_progress)
            async with AsyncSession(engine) as session:
                session.add_all(all_db_objects)
                await session.commit()
            await queue.put(save_progress.model_copy(update={"step": 1}))

            await queue.put(DoneData())

        except Exception:
            logger.exception("Processing failed")
            await queue.put(
                ErrorData(
                    detail="Processing failed. Please try again later.",
                )
            )
        finally:
            await queue.put(None)  # sentinel

    task = asyncio.create_task(run())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@router.get(
    "/process",
    response_class=EventSourceResponse,
    responses={200: {"model": list[ProcessingEvent]}},
)
async def process_user(
    uid: Annotated[int | None, Cookie()] = None,
) -> AsyncIterable[ProcessingEvent]:
    # Fetch user in a short-lived session — the SSE stream runs for minutes,
    # so we must not hold a DB connection open via the UserDep dependency.
    if uid is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    async with AsyncSession(engine) as session:
        user = await session.get(User, uid)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    async for event in _process_stream(user):
        yield event


# ---------------------------------------------------------------------------
# Existing CRUD endpoints
# ---------------------------------------------------------------------------


class UserWithAlbumIds(BaseModel):
    user: User
    album_ids: list[str]


@router.get("")
async def read_user(user: UserDep, session: SessionDep) -> UserWithAlbumIds:
    album_ids = list(
        (await session.scalars(select(Album.id).where(Album.uid == user.id))).all()
    )
    return UserWithAlbumIds(user=user, album_ids=album_ids)


class UserSettings(BaseModel):
    unit_is_km: bool | None = None
    temperature_is_celsius: bool | None = None
    locale: str | None = None


@router.patch("")
async def update_user(update: UserSettings, user: UserDep, session: SessionDep) -> User:
    if update.unit_is_km is not None:
        user.unit_is_km = update.unit_is_km
    if update.temperature_is_celsius is not None:
        user.temperature_is_celsius = update.temperature_is_celsius
    if update.locale is not None:
        user.locale = update.locale
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# noinspection PyTypeChecker
@router.delete("")
async def delete_user(user: UserDep, session: SessionDep, response: Response) -> None:
    await asyncio.to_thread(shutil.rmtree, user.folder)
    await session.delete(user)
    await session.commit()
    response.delete_cookie(USER_COOKIE)
