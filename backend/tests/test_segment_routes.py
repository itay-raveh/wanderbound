from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from fastapi import BackgroundTasks
from sqlmodel.ext.asyncio.session import AsyncSession

from app.logic.segment_routes import (
    album_route_enrichment_workflow,
    enqueue_album_route_enrichment,
    match_album_segment_routes,
    route_enrichment_payload,
    route_enrichment_workflow_id,
    start_album_route_enrichment,
)
from app.models.segment import Segment, SegmentKind

from .factories import AID, insert_album, insert_segment

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

type Route = list[tuple[float, float]]
type SegmentSeed = tuple[float, float, SegmentKind]


@asynccontextmanager
async def _lock(*, acquired: bool = True) -> AsyncIterator[bool]:
    yield acquired


def _http() -> SimpleNamespace:
    return SimpleNamespace(mapbox_matching=object(), mapbox_directions=object())


def _stats(
    *, requests: int = 1, matching_requests: int = 1, directions_requests: int = 0
) -> SimpleNamespace:
    return SimpleNamespace(
        requests=requests,
        matching_requests=matching_requests,
        directions_requests=directions_requests,
    )


async def _seed_segments(engine: AsyncEngine, uid: int, *segments: SegmentSeed) -> None:
    async with AsyncSession(engine) as session:
        await insert_album(session, uid)
        for start_time, end_time, kind in segments:
            await insert_segment(
                session,
                uid,
                start_time=start_time,
                end_time=end_time,
                kind=kind,
            )
        await session.commit()


async def _run_route_enrichment(
    engine: AsyncEngine,
    uid: int,
    *,
    http: SimpleNamespace | None = None,
    lock_acquired: bool = True,
    route_result: tuple[list[Route | None], SimpleNamespace] | None = None,
    side_effect: object | None = None,
) -> SimpleNamespace:
    http = http or _http()
    match_segments = AsyncMock(
        side_effect=side_effect,
        return_value=route_result or ([], _stats(requests=0, matching_requests=0)),
    )

    with (
        patch("app.logic.segment_routes.get_engine", return_value=engine) as get_engine,
        patch(
            "app.logic.segment_routes.try_advisory_lock",
            return_value=_lock(acquired=lock_acquired),
        ),
        patch(
            "app.logic.segment_routes.match_segments_with_stats",
            new=match_segments,
        ),
    ):
        await match_album_segment_routes(http, uid, AID)

    return SimpleNamespace(
        get_engine=get_engine,
        match_segments=match_segments,
        http=http,
    )


def test_enqueue_album_route_enrichment_adds_background_task() -> None:
    background_tasks = BackgroundTasks()
    http = _http()

    enqueue_album_route_enrichment(background_tasks, http, 123, "album-1")

    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is start_album_route_enrichment
    assert task.args == (123, "album-1")
    assert task.kwargs == {}


def test_start_album_route_enrichment_uses_stable_workflow_id() -> None:
    calls: list[tuple[object, dict[str, object]]] = []
    workflow_ids: list[str] = []
    handle = object()

    class FakeSetWorkflowID:
        def __init__(self, workflow_id: str) -> None:
            self.workflow_id = workflow_id

        def __enter__(self) -> None:
            workflow_ids.append(self.workflow_id)

        def __exit__(self, *args: object) -> None:
            return None

    def fake_start_workflow(func: object, payload: dict[str, object]) -> object:
        calls.append((func, payload))
        return handle

    with (
        patch("app.logic.segment_routes.SetWorkflowID", FakeSetWorkflowID),
        patch("app.logic.segment_routes.DBOS.start_workflow", fake_start_workflow),
    ):
        result = start_album_route_enrichment(123, "album-1")

    assert result is handle
    assert workflow_ids == [route_enrichment_workflow_id(123, "album-1")]
    assert calls == [
        (album_route_enrichment_workflow, route_enrichment_payload(123, "album-1"))
    ]


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
    await _seed_segments(
        engine,
        uid,
        (100.0, 200.0, SegmentKind.driving),
        (300.0, 400.0, SegmentKind.walking),
    )

    result = await _run_route_enrichment(
        engine,
        uid,
        route_result=(
            [driving_route, walking_route],
            _stats(requests=2, matching_requests=1, directions_requests=1),
        ),
    )

    assert (
        await _route_for(engine, uid, start_time=100.0, end_time=200.0) == driving_route
    )
    assert (
        await _route_for(engine, uid, start_time=300.0, end_time=400.0) == walking_route
    )
    match_segments = result.match_segments
    match_segments.assert_awaited_once()
    assert match_segments.await_args.args[:2] == (
        result.http.mapbox_matching,
        result.http.mapbox_directions,
    )
    assert [profile for _, profile in match_segments.await_args.args[2]] == [
        "driving",
        "walking",
    ]


async def test_hike_and_flight_segments_are_skipped(engine: AsyncEngine) -> None:
    uid = 3002
    await _seed_segments(
        engine,
        uid,
        (100.0, 200.0, SegmentKind.hike),
        (300.0, 400.0, SegmentKind.flight),
    )

    result = await _run_route_enrichment(engine, uid)
    result.match_segments.assert_not_awaited()
    assert await _route_for(engine, uid, start_time=100.0, end_time=200.0) is None
    assert await _route_for(engine, uid, start_time=300.0, end_time=400.0) is None


async def test_rows_deleted_before_write_are_skipped(engine: AsyncEngine) -> None:
    uid = 3003
    route = [(4.0, 52.0), (4.1, 52.1)]
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))

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

    await _run_route_enrichment(engine, uid, side_effect=delete_then_match)

    async with AsyncSession(engine) as session:
        assert await session.get(Segment, (uid, AID, 100.0, 200.0)) is None


async def test_none_route_leaves_row_unchanged(engine: AsyncEngine) -> None:
    uid = 3004
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))
    await _run_route_enrichment(
        engine,
        uid,
        route_result=([None], _stats()),
    )

    assert await _route_for(engine, uid) is None


async def test_advisory_lock_already_held_skips_run(engine: AsyncEngine) -> None:
    uid = 3005
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))
    result = await _run_route_enrichment(engine, uid, lock_acquired=False)

    result.get_engine.assert_not_called()
    result.match_segments.assert_not_awaited()
    assert await _route_for(engine, uid) is None
