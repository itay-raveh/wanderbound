import asyncio
import shutil
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from pathlib import Path

import structlog
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.http_clients import HttpClients
from app.logic.demo_i18n import apply_overlay, load_overlay
from app.logic.reconcile import reconcile_trip
from app.logic.trip_processing import (
    DbRow,
    ErrorData,
    PhaseUpdate,
    ProcessingEvent,
    TripResults,
    TripStart,
    _media_pipeline,
    build_trip_objects,
    count_segments,
    cover_name_from_trip,
    drain_queue,
    load_trip_data,
    run_elevations,
    run_weather,
)
from app.models.album import Album
from app.models.segment import Segment
from app.models.step import Step
from app.models.user import User

logger = structlog.get_logger(__name__)

_POLARSTEPS_METADATA = {"trip.json", "locations.json"}


def _cleanup_metadata(user_folder: Path, trip_dirs: list[Path]) -> None:
    """Free disk and avoid leaking raw location history after ingestion."""
    for td in trip_dirs:
        for name in _POLARSTEPS_METADATA:
            (td / name).unlink(missing_ok=True)

    shutil.rmtree(user_folder / "user", ignore_errors=True)

    logger.debug("processing.metadata_cleaned", user_folder=user_folder.name)


async def _process_trip(
    http: HttpClients,
    user: User,
    trip_dir: Path,
    db_out: list[DbRow],
) -> AsyncIterator[ProcessingEvent]:
    aid = trip_dir.name
    trip, locations = await asyncio.to_thread(load_trip_data, trip_dir)
    logger.info(
        "processing.trip_started",
        album_id=aid,
        step_count=trip.step_count,
    )
    locs = [s.location for s in trip.all_steps]

    queue: asyncio.Queue[PhaseUpdate | None] = asyncio.Queue()
    cover_name = cover_name_from_trip(trip)
    n = len(trip.all_steps)

    async def _phases() -> TripResults:
        try:
            async with asyncio.TaskGroup() as tg:
                elev_task = tg.create_task(run_elevations(http, locs, n, queue))
                weather_task = tg.create_task(
                    run_weather(http, trip.all_steps, n, queue)
                )
                media_task = tg.create_task(
                    _media_pipeline(user, trip, trip_dir, cover_name, queue)
                )
        finally:
            await queue.put(None)
        layout_by_idx, final_cover_name = media_task.result()
        return TripResults(
            elevations=elev_task.result(),
            weather_by_idx=weather_task.result(),
            layout_by_idx=layout_by_idx,
            cover_name=final_cover_name,
        )

    runner = asyncio.create_task(_phases())
    async for event in drain_queue(runner, queue):
        yield event

    results = await runner
    yield PhaseUpdate(phase="segments", done=0, total=1)
    objects = await asyncio.to_thread(
        build_trip_objects, user, aid, trip, locations, results
    )
    segments = [obj for obj in objects if isinstance(obj, Segment)]
    yield PhaseUpdate(phase="segments", done=1, total=1)
    yield count_segments(segments)
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
    logger.info(
        "processing.db_saved",
        user_id=uid,
        object_count=len(objects),
        new_user=True,
    )


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
                .where(col(Step.uid) == uid)
                .where(col(Step.aid).in_(reconciled_aids))
            )
            await session.exec(
                delete(Segment)
                .where(col(Segment.uid) == uid)
                .where(col(Segment.aid).in_(reconciled_aids))
            )

        current_aids = {d.name for d in trip_dirs}
        orphan_aids = set(existing_albums) - current_aids
        if orphan_aids:
            await session.exec(
                delete(Album)
                .where(col(Album.uid) == uid)
                .where(col(Album.id).in_(orphan_aids))
            )
        await session.flush()

        for obj in objects:
            await session.merge(obj)
        await session.commit()
    logger.info(
        "processing.db_saved",
        user_id=uid,
        object_count=len(objects),
        new_user=False,
    )


def _apply_demo_i18n(user: User, all_objects: list[DbRow]) -> None:
    if not user.is_demo:
        return
    overlay = load_overlay(user.locale, get_settings().DEMO_FIXTURES)
    if overlay is None:
        return

    albums: list[Album] = []
    steps_by_aid: dict[str, list[Step]] = defaultdict(list)
    for o in all_objects:
        if isinstance(o, Album):
            albums.append(o)
        elif isinstance(o, Step):
            steps_by_aid[o.aid].append(o)

    for album in albums:
        apply_overlay(overlay, album, steps_by_aid.get(album.id, []))

    logger.info("demo.i18n_overlay_applied", user_id=user.id, locale=user.locale)


async def run_processing(
    http: HttpClients, user: User
) -> AsyncIterator[ProcessingEvent]:
    t0 = time.monotonic()
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
                    http,
                    user,
                    trip_dir,
                    existing_albums[aid],
                    existing_steps.get(aid, []),
                    all_objects,
                ):
                    yield event
                reconciled_aids.add(aid)
            else:
                async for event in _process_trip(http, user, trip_dir, all_objects):
                    yield event
    except Exception:
        logger.exception("processing.failed", user_id=user.id)
        yield ErrorData()
        return

    _apply_demo_i18n(user, all_objects)

    try:
        if existing_albums:
            await _save_reupload(
                user.id, all_objects, reconciled_aids, existing_albums, trip_dirs
            )
        else:
            await _save_new(user.id, all_objects)
    except SQLAlchemyError:
        logger.exception("processing.db_save_failed", user_id=user.id)
        yield ErrorData()
        return
    await asyncio.to_thread(_cleanup_metadata, user.folder, trip_dirs)
    logger.info(
        "processing.completed",
        user_id=user.id,
        trip_count=len(trip_dirs),
        duration_s=time.monotonic() - t0,
    )
