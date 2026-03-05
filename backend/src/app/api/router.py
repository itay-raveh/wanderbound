# ruff: noqa: ARG001, TC001, TC003
# pyright: reportUnusedParameter=false

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, timedelta
from itertools import chain
from pathlib import Path
from zipfile import BadZipFile

from fastapi import APIRouter, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from safezip import SafezipError, SafeZipFile
from sqlmodel import select

from app.core.client import APIClient
from app.core.logging import config_logger
from app.logic.data.country_colors import build_country_colors
from app.logic.data.openmeteo import fetch_elevations
from app.logic.data.weather import fetch_weather
from app.logic.layout.builder import build_step_layout
from app.logic.layout.media import extract_frame
from app.logic.segments import Segment, build_segments, clean_points
from app.models.db import (
    Album,
    AlbumId,
    AlbumSettings,
    Step,
    StepIdx,
    StepLayout,
    User,
)
from app.models.polarsteps import PSLocations, PSPoint, PSTrip

from .deps import DependsAlbum, DependsSession, DependsUser

logger = config_logger(__name__)

api = APIRouter()


@api.post("/upload")
async def upload(
    session: DependsSession,
    file: UploadFile,
    response: Response,
) -> None:
    user = User()
    session.add(user)
    response.set_cookie("uid", str(user.id))

    logger.info("New user: %s", user)
    logger.info(
        "Extracting '%s' (%d MB)",
        file.filename,
        (file.size or 0) // 1024 // 1024,
    )

    # Extract ZIP
    try:
        with SafeZipFile(file.file) as zf:
            await asyncio.to_thread(zf.extractall, user.folder)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    except (BadZipFile, SafezipError) as e:
        raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail=str(e)) from e

    for trip_folder in user.trip_folder.iterdir():
        logger.info("Processing '%s' ...", trip_folder.name)

        # Load trip.json
        trip = PSTrip.model_validate_json((trip_folder / "trip.json").read_bytes())

        logger.info("Loaded '%s' with %d steps", trip.title, trip.step_count)

        # Create color palette
        colors = build_country_colors({ps_step.location.country_code for ps_step in trip.all_steps})

        for code, color in colors.items():
            logger.info("[%s] ███ %s ███ [/]", color, code)

        # Create Album
        album = Album(
            uid=user.id,
            id=trip_folder.name,
            colors=colors,
            steps_ranges=f"0-{trip.step_count - 1}",
            title=trip.title,
            subtitle=trip.subtitle,
            front_cover_photo=str(trip.cover_photo.path),
            back_cover_photo=str(trip.cover_photo.path),
        )

        session.add(album)

        async with APIClient() as client:
            elevations = [
                int(el)
                async for el in fetch_elevations(
                    client, [ps_step.location for ps_step in trip.all_steps]
                )
            ]

            logger.info(":heavy_check_mark: Fetched elevations")

            weathers = await asyncio.gather(
                *(fetch_weather(client, step) for step in trip.all_steps)
            )

            logger.info(":heavy_check_mark: Fetched weathers")

            layouts = (
                # await asyncio.gather(
                # *(
                [await build_step_layout(user, album.id, step) for step in trip.all_steps]
                # )
                # )
            )

            logger.info(":heavy_check_mark: Fetched layouts")

        # Create steps
        for idx, (step, elevation, weather, (cover, pages)) in enumerate(
            zip(trip.all_steps, elevations, weathers, layouts, strict=True)
        ):
            logger.info('Step %d "%s"', idx, step.name)

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
    step = await session.get_one(Step, (user.id, aid, sid))
    step.sqlmodel_update(update)
    session.add(step)
    await session.commit()
    await session.refresh(step)
    # noinspection PyTypeChecker
    return step


@api.get("/albums/{aid}/segments")
async def get_segments(
    aid: AlbumId,
    first: StepIdx,
    last: StepIdx,
    user: DependsUser,
    session: DependsSession,
) -> Sequence[Segment]:
    # Get GPS data
    locations = PSLocations.model_validate_json(
        (user.trip_folder / aid / "locations.json").read_bytes()
    )

    # Get steps (we want to add them as GPS points as well)
    steps = (
        await session.scalars(
            select(Step).where(
                Step.uid == user.id, Step.aid == aid, Step.idx >= first, Step.idx <= last
            )
        )
    ).all()

    buffer = timedelta(days=0.5)

    # Combine and filter to get all points between the steps
    points = filter(
        lambda point: (
            (steps[0].datetime - buffer) <= point.datetime <= (steps[-1].datetime + buffer)
        ),
        chain(
            clean_points(locations.locations),
            (
                PSPoint(
                    lat=step.location.lat,
                    lon=step.location.lon,
                    time=step.datetime.timestamp(),
                )
                for step in steps
            ),
        ),
    )

    segments = list(build_segments(points))
    logger.info("Found %d segments for %s", len(segments), aid)

    flights = [seg for seg in segments if seg.kind == "flight"]
    logger.info("Found %d flights for %s", len(flights), aid)

    return segments


@api.get("/trip/{asset_rel_path:path}")
async def get_trip_asset(asset_rel_path: Path, user: DependsUser) -> FileResponse:
    asset_path = user.trip_folder / asset_rel_path

    if asset_path.suffix.lower() not in {".jpg", ".png", ".mp4"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    try:
        asset_path_resolved = asset_path.resolve()
    except OSError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND) from e

    if (
        not asset_path_resolved.is_relative_to(user.trip_folder)
        or not asset_path_resolved.is_file()
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    return FileResponse(asset_path_resolved)


@api.put("/trip/{video:path}")
async def update_video_frame(video: Path, timestamp: int) -> None:
    await extract_frame(video, timestamp)
