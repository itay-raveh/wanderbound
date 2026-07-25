import asyncio
import shutil
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import structlog
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.http_clients import HttpClients
from app.core.observability import start_span
from app.logic.demo_i18n import apply_overlay, load_overlay
from app.logic.reconcile import reconcile_trip
from app.logic.step_media import read_steps_with_media
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
from app.models.album_media import AlbumMedia, StepPageMedia, StepUnusedMedia
from app.models.segment import Segment
from app.models.step import Step, StepRead
from app.models.user import User

logger = structlog.get_logger(__name__)

_POLARSTEPS_METADATA = {"trip.json", "locations.json"}
SaveGuard = Callable[[AsyncSession], Awaitable[bool]]


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
    with start_span(
        "processing.load_trip",
        "Load trip data",
        **{"app.workflow": "processing", "album.id": aid},
    ):
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

    with start_span(
        "processing.trip",
        "Process trip",
        **{
            "app.workflow": "processing",
            "user.id": user.id,
            "album.id": aid,
            "step.count": n,
        },
    ):
        runner = asyncio.create_task(_phases())
        async for event in drain_queue(runner, queue):
            yield event

        results = await runner
        yield PhaseUpdate(phase="segments", done=0, total=1)
        with start_span(
            "processing.build_objects",
            "Build trip objects",
            **{
                "app.workflow": "processing",
                "user.id": user.id,
                "album.id": aid,
                "step.count": n,
                "location.count": len(locations),
            },
        ):
            objects = await asyncio.to_thread(
                build_trip_objects, user, aid, trip, trip_dir, locations, results
            )
        segments = [obj for obj in objects if isinstance(obj, Segment)]
        yield PhaseUpdate(phase="segments", done=1, total=1)
        yield count_segments(segments)
        db_out.extend(objects)


async def _load_existing(
    user: User,
) -> tuple[dict[str, Album], dict[str, list[AlbumMedia]], dict[str, list[StepRead]]]:
    """Load existing albums and steps for reconciliation.

    Returns empty dicts for new users (no albums yet).
    """
    if not user.album_ids:
        return {}, {}, {}

    with start_span(
        "processing.load_existing",
        "Load existing albums",
        **{"app.workflow": "processing", "user.id": user.id},
    ):
        async with AsyncSession(get_engine(), expire_on_commit=False) as session:
            albums = {
                a.id: a
                for a in (
                    await session.exec(select(Album).where(Album.uid == user.id))
                ).all()
            }

            media_by_aid: dict[str, list[AlbumMedia]] = defaultdict(list)
            for media in (
                await session.exec(select(AlbumMedia).where(AlbumMedia.uid == user.id))
            ).all():
                media_by_aid[media.aid].append(media)

            steps_by_aid = {
                aid: await read_steps_with_media(session, user.id, aid)
                for aid in albums
            }

    return albums, dict(media_by_aid), dict(steps_by_aid)


async def _save_new(
    uid: int,
    objects: list[DbRow],
    *,
    save_guard: SaveGuard | None = None,
) -> bool:
    with start_span(
        "processing.db_save",
        "Save processing results",
        **{
            "app.workflow": "processing",
            "user.id": uid,
            "object.count": len(objects),
            "new_user": True,
        },
    ):
        async with AsyncSession(get_engine()) as session:
            if save_guard is not None and not await save_guard(session):
                logger.info("processing.stale_during_save", user_id=uid)
                return False
            await _add_new_objects(session, objects)
            await session.commit()
    logger.info(
        "processing.db_saved",
        user_id=uid,
        object_count=len(objects),
        new_user=True,
    )
    return True


async def _add_new_objects(session: AsyncSession, objects: list[DbRow]) -> None:
    for model in (Album, AlbumMedia, Step, StepPageMedia, StepUnusedMedia, Segment):
        rows = [obj for obj in objects if isinstance(obj, model)]
        if rows:
            session.add_all(rows)
            await session.flush()


async def _save_reupload(  # noqa: PLR0913
    uid: int,
    objects: list[DbRow],
    reconciled_aids: set[str],
    existing_albums: dict[str, Album],
    trip_dirs: list[Path],
    *,
    album_ids: tuple[str, ...] | None = None,
    save_guard: SaveGuard | None = None,
) -> bool:
    with start_span(
        "processing.db_save",
        "Save processing results",
        **{
            "app.workflow": "processing",
            "user.id": uid,
            "object.count": len(objects),
            "album.count": len(trip_dirs),
            "reconciled_album.count": len(reconciled_aids),
            "new_user": False,
        },
    ):
        async with AsyncSession(get_engine()) as session:
            if save_guard is not None and not await save_guard(session):
                logger.info("processing.stale_during_save", user_id=uid)
                return False
            if reconciled_aids:
                await session.exec(
                    delete(StepPageMedia)
                    .where(col(StepPageMedia.uid) == uid)
                    .where(col(StepPageMedia.aid).in_(reconciled_aids))
                )
                await session.exec(
                    delete(StepUnusedMedia)
                    .where(col(StepUnusedMedia.uid) == uid)
                    .where(col(StepUnusedMedia.aid).in_(reconciled_aids))
                )
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
                await session.exec(
                    delete(AlbumMedia)
                    .where(col(AlbumMedia.uid) == uid)
                    .where(col(AlbumMedia.aid).in_(reconciled_aids))
                )

            current_aids = {d.name for d in trip_dirs}
            expected_aids = (
                set(existing_albums) if album_ids is None else set(album_ids)
            )
            orphan_aids = expected_aids - current_aids
            if orphan_aids:
                await session.exec(
                    delete(Album)
                    .where(col(Album.uid) == uid)
                    .where(col(Album.id).in_(orphan_aids))
                )
            await session.flush()

            await _merge_objects(session, objects)
            await session.commit()
    logger.info(
        "processing.db_saved",
        user_id=uid,
        object_count=len(objects),
        new_user=False,
    )
    return True


async def _merge_objects(session: AsyncSession, objects: list[DbRow]) -> None:
    for model in (Album, AlbumMedia, Step, StepPageMedia, StepUnusedMedia, Segment):
        rows = [obj for obj in objects if isinstance(obj, model)]
        for obj in rows:
            await session.merge(obj)
        if rows:
            await session.flush()


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


async def _processing_should_continue(
    user: User, should_continue: Callable[[], Awaitable[bool]] | None
) -> bool:
    if should_continue is None or await should_continue():
        return True
    logger.info("processing.stale_before_save", user_id=user.id)
    return False


async def run_processing(  # noqa: C901
    http: HttpClients,
    user: User,
    *,
    album_ids: tuple[str, ...] | None = None,
    should_continue: Callable[[], Awaitable[bool]] | None = None,
    save_guard: SaveGuard | None = None,
) -> AsyncIterator[ProcessingEvent]:
    t0 = time.monotonic()
    trip_dirs = (
        sorted(user.trips_folder.iterdir())
        if album_ids is None
        else [user.trips_folder / aid for aid in album_ids]
    )

    all_objects: list[DbRow] = []
    reconciled_aids: set[str] = set()
    with start_span(
        "processing.run",
        "Run processing",
        **{
            "app.workflow": "processing",
            "user.id": user.id,
            "album.count": len(trip_dirs),
        },
    ):
        existing_albums, existing_media, existing_steps = await _load_existing(user)
        try:
            for trip_idx, trip_dir in enumerate(trip_dirs):
                aid = trip_dir.name
                yield TripStart(trip_index=trip_idx)

                if aid in existing_albums:
                    with start_span(
                        "processing.reconcile_trip",
                        "Reconcile trip",
                        **{
                            "app.workflow": "processing",
                            "user.id": user.id,
                            "album.id": aid,
                            "existing_step.count": len(existing_steps.get(aid, [])),
                        },
                    ):
                        async for event in reconcile_trip(
                            http,
                            user,
                            trip_dir,
                            existing_albums[aid],
                            existing_steps.get(aid, []),
                            all_objects,
                            existing_media.get(aid, []),
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

        if not await _processing_should_continue(user, should_continue):
            yield ErrorData()
            return

        try:
            if existing_albums:
                saved = await _save_reupload(
                    user.id,
                    all_objects,
                    reconciled_aids,
                    existing_albums,
                    trip_dirs,
                    album_ids=album_ids,
                    save_guard=save_guard,
                )
            else:
                saved = await _save_new(user.id, all_objects, save_guard=save_guard)
        except SQLAlchemyError:
            logger.exception("processing.db_save_failed", user_id=user.id)
            yield ErrorData()
            return
        if not saved:
            yield ErrorData()
            return
        with start_span(
            "processing.cleanup",
            "Clean processing metadata",
            **{
                "app.workflow": "processing",
                "user.id": user.id,
                "album.count": len(trip_dirs),
            },
        ):
            await asyncio.to_thread(_cleanup_metadata, user.folder, trip_dirs)
        logger.info(
            "processing.completed",
            user_id=user.id,
            trip_count=len(trip_dirs),
            duration_s=time.monotonic() - t0,
        )
