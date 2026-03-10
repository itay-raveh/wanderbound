import asyncio
import shutil
from zipfile import BadZipFile

from fastapi import APIRouter, HTTPException, Response, UploadFile, status
from safezip import SafezipError

from app.core.logging import config_logger
from app.logic.country_colors import build_country_colors
from app.logic.layout import build_step_layout
from app.logic.open_meteo import elevations
from app.logic.weather import build_weather
from app.models.db import Album, Step, User
from app.models.trips import Trip

from ..deps import USER_COOKIE, SessionDep, UserDep

logger = config_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/")
async def create_user(file: UploadFile, session: SessionDep, response: Response) -> User:
    try:
        user = await asyncio.to_thread(User.from_zip_upload, file.file)
    except (BadZipFile, SafezipError, OSError) as e:
        logger.warning("Bad ZIP: %s", e)
        raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail="Bad ZIP") from e

    session.add(user)
    response.set_cookie(USER_COOKIE, str(user.id))

    for trip_dir in user.trips_folder.iterdir():
        trip = Trip.from_trip_dir(trip_dir)
        trip.all_steps.sort()
        logger.info("Processing '%s' with %d steps...", trip.title, trip.step_count)

        colors = build_country_colors({ps_step.location.country_code for ps_step in trip.all_steps})

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

        session.add(album)

        elevs = [int(elev) async for elev in elevations(step.location for step in trip.all_steps)]
        logger.info(":heavy_check_mark: Fetched elevations")

        weathers = await asyncio.gather(*(build_weather(step) for step in trip.all_steps))
        logger.info(":heavy_check_mark: Fetched weathers")

        layouts = await asyncio.gather(
            *(build_step_layout(user, album.id, step) for step in trip.all_steps)
        )
        logger.info(":heavy_check_mark: Built layouts")

        for idx, (step, elevation, weather, (cover, pages)) in enumerate(
            zip(trip.all_steps, elevs, weathers, layouts, strict=True)
        ):
            # Add step
            session.add(
                Step(
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
            )

    await session.commit()
    await session.refresh(user)
    return user


@router.delete("/")
async def delete_user(user: UserDep, session: SessionDep, response: Response) -> None:
    await asyncio.to_thread(shutil.rmtree, user.folder)
    await session.delete(user)
    await session.commit()
    response.delete_cookie(USER_COOKIE)
