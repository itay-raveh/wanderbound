# ruff: noqa: ARG001, TC003
# pyright: reportUnusedParameter=false

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Sequence
from itertools import chain
from pathlib import Path
from zipfile import BadZipFile

from fastapi import APIRouter, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from safezip import SafezipError
from sqlmodel import select

from app.core.logging import config_logger
from app.logic.country_colors import build_country_colors
from app.logic.layout import build_step_layout
from app.logic.layout.media import extract_frame
from app.logic.open_meteo import elevations
from app.logic.spatial.segments import Segment, build_segments
from app.logic.weather import build_weather
from app.models.db import (
    Album,
    AlbumId,
    AlbumSettings,
    Step,
    StepIdx,
    StepLayout,
    User,
)
from app.models.trips import Locations, Trip

from .deps import USER_COOKIE, DependsAlbum, DependsSession, DependsUser

logger = config_logger(__name__)

api = APIRouter()


@api.post("/users")
async def create_user(
    file: UploadFile,
    session: DependsSession,
    response: Response,
) -> User:
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


@api.delete("/users")
async def delete_user(user: DependsUser, session: DependsSession, response: Response) -> None:
    shutil.rmtree(user.folder)
    await session.delete(user)
    await session.commit()
    response.delete_cookie(USER_COOKIE)


@api.get("/albums")
async def get_album_names(user: DependsUser, session: DependsSession) -> Sequence[str]:
    return (await session.scalars(select(Album.id).where(Album.uid == user.id))).all()


@api.get("/albums/{aid}")
async def get_album(aid: AlbumId, album: DependsAlbum) -> Album:
    return album


@api.put("/albums/{aid}")
async def update_album_settings(
    aid: AlbumId,
    update: AlbumSettings,
    album: DependsAlbum,
    session: DependsSession,
) -> Album:
    album.sqlmodel_update(update)
    session.add(album)
    await session.commit()
    await session.refresh(album)
    return album


class Range(BaseModel):
    start: int
    end: int


@api.post("/albums/{aid}/steps")
async def get_step_ranges(
    aid: AlbumId,
    ranges: list[Range],
    user: DependsUser,
    session: DependsSession,
) -> Sequence[Step]:
    indexes = list(chain(*(range(rng.start, rng.end + 1) for rng in ranges)))

    # noinspection PyUnresolvedReferences
    return (
        await session.scalars(
            select(Step)
            .where(
                Step.uid == user.id,
                Step.aid == aid,
                Step.idx.in_(indexes),  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportAttributeAccessIssue]
            )
            .order_by(Step.idx)  # pyright: ignore[reportArgumentType]
        )
    ).all()


@api.put("/albums/{aid}/steps/{sid}")
async def update_step_layout(
    aid: AlbumId,
    sid: StepIdx,
    update: StepLayout,
    user: DependsUser,
    session: DependsSession,
) -> Step:
    # noinspection PyTypeChecker
    step: Step = await session.get_one(Step, (user.id, aid, sid))
    step.sqlmodel_update(update)
    session.add(step)
    await session.commit()
    await session.refresh(step)
    return step


@api.get("/albums/{aid}/segments")
async def get_segments(
    aid: AlbumId,
    first: StepIdx,
    last: StepIdx,
    user: DependsUser,
    session: DependsSession,
) -> Sequence[Segment]:
    # Get steps ordered by time
    stmt = (
        select(Step)
        .where(Step.uid == user.id, Step.aid == aid, Step.idx >= first, Step.idx <= last)
        .order_by(Step.idx)  # pyright: ignore[reportArgumentType]
    )
    steps = (await session.scalars(stmt)).all()
    locations = Locations.from_trip_dir(user.trips_folder / aid).locations
    return list(build_segments(steps, locations))


@api.get("/trip/{asset_rel_path:path}")
async def get_trip_asset(asset_rel_path: Path, user: DependsUser) -> FileResponse:
    normalized = (user.trips_folder / asset_rel_path).resolve()

    if (
        normalized.suffix.lower() not in {".jpg", ".jpeg", ".png", ".mp4"}
        or not normalized.is_relative_to(user.trips_folder)
        or not normalized.is_file(follow_symlinks=False)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    return FileResponse(normalized)


@api.put("/trip/{video:path}")
async def update_video_frame(video: Path, timestamp: int) -> None:
    await extract_frame(video, timestamp)
