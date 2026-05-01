from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from fastapi import BackgroundTasks
from sqlmodel.ext.asyncio.session import AsyncSession

from app.logic.segment_routes import (
    enqueue_album_route_enrichment,
    match_album_segment_routes,
)
from app.models.segment import Segment, SegmentKind

from .factories import AID, insert_album, insert_segment

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@asynccontextmanager
async def _lock(*, acquired: bool = True) -> AsyncIterator[bool]:
    yield acquired


def _http() -> SimpleNamespace:
    return SimpleNamespace(mapbox_matching=object(), mapbox_directions=object())


def test_enqueue_album_route_enrichment_adds_background_task() -> None:
    background_tasks = BackgroundTasks()
    http = _http()

    enqueue_album_route_enrichment(background_tasks, http, 123, "album-1")

    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is match_album_segment_routes
    assert task.args == (http, 123, "album-1")
    assert task.kwargs == {}


async def _route_for(
    engine: AsyncEngine,
    uid: int,
    aid: str = AID,
    start_time: float = 100.0,
    end_time: float = 200.0,
) -> list[tuple[float, float]] | None:
    async with AsyncSession(engine) as session:
        seg = await session.get(Segment, (uid, aid, start_time, end_time))
        assert seg is not None
        return seg.route


async def test_unmatched_driving_and_walking_segments_get_routes(
    engine: AsyncEngine,
) -> None:
    uid = 3001
    driving_route = [(4.0, 52.0), (4.1, 52.1)]
    walking_route = [(5.0, 53.0), (5.1, 53.1)]
    async with AsyncSession(engine) as session:
        await insert_album(session, uid)
        await insert_segment(
            session,
            uid,
            start_time=100.0,
            end_time=200.0,
            kind=SegmentKind.driving,
        )
        await insert_segment(
            session,
            uid,
            start_time=300.0,
            end_time=400.0,
            kind=SegmentKind.walking,
        )
        await session.commit()

    http = _http()
    with (
        patch("app.logic.segment_routes.get_engine", return_value=engine),
        patch("app.logic.segment_routes.try_advisory_lock", return_value=_lock()),
        patch(
            "app.logic.segment_routes.match_segments_with_stats",
            new=AsyncMock(
                return_value=(
                    [driving_route, walking_route],
                    SimpleNamespace(
                        requests=2,
                        matching_requests=1,
                        directions_requests=1,
                    ),
                )
            ),
        ) as match_segments,
    ):
        await match_album_segment_routes(http, uid, AID)

    assert (
        await _route_for(engine, uid, start_time=100.0, end_time=200.0) == driving_route
    )
    assert (
        await _route_for(engine, uid, start_time=300.0, end_time=400.0) == walking_route
    )
    match_segments.assert_awaited_once()
    assert match_segments.await_args.args[:2] == (
        http.mapbox_matching,
        http.mapbox_directions,
    )
    assert [profile for _, profile in match_segments.await_args.args[2]] == [
        "driving",
        "walking",
    ]


async def test_hike_and_flight_segments_are_skipped(engine: AsyncEngine) -> None:
    uid = 3002
    async with AsyncSession(engine) as session:
        await insert_album(session, uid)
        await insert_segment(
            session,
            uid,
            start_time=100.0,
            end_time=200.0,
            kind=SegmentKind.hike,
        )
        await insert_segment(
            session,
            uid,
            start_time=300.0,
            end_time=400.0,
            kind=SegmentKind.flight,
        )
        await session.commit()

    with (
        patch("app.logic.segment_routes.get_engine", return_value=engine),
        patch("app.logic.segment_routes.try_advisory_lock", return_value=_lock()),
        patch(
            "app.logic.segment_routes.match_segments_with_stats", new=AsyncMock()
        ) as match_segments,
    ):
        await match_album_segment_routes(_http(), uid, AID)

    match_segments.assert_not_awaited()
    assert await _route_for(engine, uid, start_time=100.0, end_time=200.0) is None
    assert await _route_for(engine, uid, start_time=300.0, end_time=400.0) is None


async def test_rows_deleted_before_write_are_skipped(engine: AsyncEngine) -> None:
    uid = 3003
    route = [(4.0, 52.0), (4.1, 52.1)]
    async with AsyncSession(engine) as session:
        await insert_album(session, uid)
        await insert_segment(
            session,
            uid,
            start_time=100.0,
            end_time=200.0,
            kind=SegmentKind.driving,
        )
        await session.commit()

    async def delete_then_match(
        *_args: object,
    ) -> tuple[list[list[tuple[float, float]]], SimpleNamespace]:
        async with AsyncSession(engine) as session:
            seg = await session.get(Segment, (uid, AID, 100.0, 200.0))
            assert seg is not None
            await session.delete(seg)
            await session.commit()
        return [route], SimpleNamespace(
            requests=1,
            matching_requests=1,
            directions_requests=0,
        )

    with (
        patch("app.logic.segment_routes.get_engine", return_value=engine),
        patch("app.logic.segment_routes.try_advisory_lock", return_value=_lock()),
        patch(
            "app.logic.segment_routes.match_segments_with_stats",
            new=AsyncMock(side_effect=delete_then_match),
        ),
    ):
        await match_album_segment_routes(_http(), uid, AID)

    async with AsyncSession(engine) as session:
        assert await session.get(Segment, (uid, AID, 100.0, 200.0)) is None


async def test_none_route_leaves_row_unchanged(engine: AsyncEngine) -> None:
    uid = 3004
    async with AsyncSession(engine) as session:
        await insert_album(session, uid)
        await insert_segment(
            session,
            uid,
            start_time=100.0,
            end_time=200.0,
            kind=SegmentKind.driving,
        )
        await session.commit()

    with (
        patch("app.logic.segment_routes.get_engine", return_value=engine),
        patch("app.logic.segment_routes.try_advisory_lock", return_value=_lock()),
        patch(
            "app.logic.segment_routes.match_segments_with_stats",
            new=AsyncMock(
                return_value=(
                    [None],
                    SimpleNamespace(
                        requests=1,
                        matching_requests=1,
                        directions_requests=0,
                    ),
                )
            ),
        ),
    ):
        await match_album_segment_routes(_http(), uid, AID)

    assert await _route_for(engine, uid) is None


async def test_advisory_lock_already_held_skips_run(engine: AsyncEngine) -> None:
    uid = 3005
    async with AsyncSession(engine) as session:
        await insert_album(session, uid)
        await insert_segment(session, uid, start_time=100.0, end_time=200.0)
        await session.commit()

    with (
        patch("app.logic.segment_routes.get_engine", return_value=engine) as get_engine,
        patch(
            "app.logic.segment_routes.try_advisory_lock",
            return_value=_lock(acquired=False),
        ),
        patch(
            "app.logic.segment_routes.match_segments_with_stats", new=AsyncMock()
        ) as match_segments,
    ):
        await match_album_segment_routes(_http(), uid, AID)

    get_engine.assert_not_called()
    match_segments.assert_not_awaited()
    assert await _route_for(engine, uid) is None
