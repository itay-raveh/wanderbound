import asyncio
import shutil
from pathlib import Path
from zipfile import BadZipFile

from fastapi import APIRouter, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from safezip import SafezipError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import config_logger
from app.logic.country_colors import build_country_colors
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


_layout_semaphore = asyncio.Semaphore(10)


async def _fetch_layouts(
    user: User,
    aid: str,
    steps: list[PSStep],
) -> list[tuple[Path, list[list[Path]]]]:
    async def _one(step: PSStep) -> tuple[Path, list[list[Path]]]:
        async with _layout_semaphore:
            return await build_step_layout(user, aid, step)

    return list(await asyncio.gather(*(_one(s) for s in steps)))


@router.post("")
async def create_user(file: UploadFile, response: Response) -> User:
    logger.info(
        "Extracting '%s' (%d MB)", file.filename, (file.size or 0) / 1024 // 1024
    )
    try:
        user = await asyncio.to_thread(User.from_zip_upload, file.file)
    except (BadZipFile, SafezipError, OSError) as e:
        logger.exception("Bad ZIP")
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Bad ZIP"
        ) from e

    response.set_cookie(USER_COOKIE, str(user.id))

    # Collect all DB objects to persist
    db_objects: list[User | Album | Step | Segment] = [user]

    for trip_dir in user.trips_folder.iterdir():
        trip = Trip.from_trip_dir(trip_dir)
        trip.all_steps.sort()
        logger.info("Processing '%s' with %d steps...", trip.title, trip.step_count)

        colors = build_country_colors(
            {ps_step.location.country_code for ps_step in trip.all_steps}
        )

        album = Album(
            uid=user.id,
            id=trip_dir.name,
            colors=colors,
            steps_ranges=f"0-{trip.step_count - 1}",
            title=trip.title,
            subtitle=trip.subtitle,
            front_cover_photo=str(trip.cover_photo.path),
            back_cover_photo=str(trip.cover_photo.path),
        )
        db_objects.append(album)

        locs = [step.location for step in trip.all_steps]
        raw = [e async for e in elevations(locs)]
        elevs = await correct_peaks(locs, raw)
        logger.info("Fetched elevations")

        weathers = [w async for w in build_weathers(trip.all_steps)]
        logger.info("Fetched weathers")

        layouts = await _fetch_layouts(user, album.id, trip.all_steps)
        logger.info("Built layouts")

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

        # Build segments from all steps + GPS locations
        locations = Locations.from_trip_dir(trip_dir).locations
        db_objects.extend(
            Segment(
                uid=user.id,
                aid=album.id,
                start_time=seg.points[0].time,
                end_time=seg.points[-1].time,
                kind=seg.kind,
                points=seg.points,
            )
            for seg in build_segments(db_steps, locations)
        )
        logger.info("Built segments")

    # Open a fresh session only for the DB write
    async with AsyncSession(engine) as session:
        existing = await session.get(User, user.id)
        if existing:
            await session.delete(existing)
            await session.flush()
        session.add_all(db_objects)
        await session.commit()
        await session.refresh(user)

    return user


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
