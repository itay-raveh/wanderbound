from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.logic.segment_routes import (
    RouteEnrichmentIncompleteError,
    album_route_enrichment_workflow,
    mark_album_route_failure_step,
    match_album_segment_routes,
    pending_route_enrichment_targets,
)
from app.models.segment import (
    RouteEnrichmentStatus,
    Segment,
    SegmentKind,
    SegmentRouteEnrichment,
)
from app.services.mapbox import MapboxTransientError, RouteMatchResult

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


def _matched(route: Route) -> RouteMatchResult:
    return RouteMatchResult(status=RouteEnrichmentStatus.matched, route=route)


def _no_route(code: str = "NoRoute") -> RouteMatchResult:
    return RouteMatchResult(
        status=RouteEnrichmentStatus.no_route,
        error_code=code,
    )


def _failed(code: str = "InvalidInput") -> RouteMatchResult:
    return RouteMatchResult(
        status=RouteEnrichmentStatus.failed,
        error_code=code,
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
    route_result: tuple[list[RouteMatchResult], SimpleNamespace] | None = None,
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
        stats = await match_album_segment_routes(http, uid, AID)

    return SimpleNamespace(
        get_engine=get_engine,
        match_segments=match_segments,
        http=http,
        stats=stats,
    )


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


async def _state_for(
    engine: AsyncEngine,
    uid: int,
    aid: str = AID,
    start_time: float = 100.0,
    end_time: float = 200.0,
) -> SegmentRouteEnrichment | None:
    async with AsyncSession(engine) as session:
        return await session.get(
            SegmentRouteEnrichment,
            (uid, aid, start_time, end_time),
        )


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
            [_matched(driving_route), _matched(walking_route)],
            _stats(requests=2, matching_requests=1, directions_requests=1),
        ),
    )

    assert (
        await _route_for(engine, uid, start_time=100.0, end_time=200.0) == driving_route
    )
    assert (
        await _route_for(engine, uid, start_time=300.0, end_time=400.0) == walking_route
    )
    first_state = await _state_for(engine, uid)
    assert first_state is not None
    assert first_state.status == RouteEnrichmentStatus.matched
    assert result.stats.updated == 2
    result.match_segments.assert_awaited_once()
    assert result.match_segments.await_args.args[:2] == (
        result.http.mapbox_matching,
        result.http.mapbox_directions,
    )
    assert [profile for _, profile in result.match_segments.await_args.args[2]] == [
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
    ) -> tuple[list[RouteMatchResult], SimpleNamespace]:
        async with AsyncSession(engine) as session:
            seg = await session.get(Segment, (uid, AID, 100.0, 200.0))
            assert seg is not None
            await session.delete(seg)
            await session.commit()
        return [_matched(route)], _stats()

    result = await _run_route_enrichment(engine, uid, side_effect=delete_then_match)

    async with AsyncSession(engine) as session:
        assert await session.get(Segment, (uid, AID, 100.0, 200.0)) is None
    assert result.stats.stale == 1


async def test_no_route_is_recorded_and_not_retried(engine: AsyncEngine) -> None:
    uid = 3004
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))
    first = await _run_route_enrichment(
        engine,
        uid,
        route_result=([_no_route("NoSegment")], _stats()),
    )
    second = await _run_route_enrichment(engine, uid)

    assert await _route_for(engine, uid) is None
    state = await _state_for(engine, uid)
    assert state is not None
    assert state.status == RouteEnrichmentStatus.no_route
    assert state.error_code == "NoSegment"
    assert first.stats.no_route == 1
    second.match_segments.assert_not_awaited()


async def test_permanent_failure_is_recorded(engine: AsyncEngine) -> None:
    uid = 3005
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))
    result = await _run_route_enrichment(
        engine,
        uid,
        route_result=([_failed()], _stats()),
    )

    state = await _state_for(engine, uid)
    assert state is not None
    assert state.status == RouteEnrichmentStatus.failed
    assert state.error_code == "InvalidInput"
    assert result.stats.failed == 1


async def test_route_matching_exception_propagates(engine: AsyncEngine) -> None:
    uid = 3006
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))

    with pytest.raises(RuntimeError, match="mapbox unavailable"):
        await _run_route_enrichment(
            engine,
            uid,
            side_effect=RuntimeError("mapbox unavailable"),
        )


async def test_exhausted_failure_marker_records_pending_segments(
    engine: AsyncEngine,
) -> None:
    uid = 3010
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))
    marker = inspect.unwrap(mark_album_route_failure_step)

    with patch("app.logic.segment_routes.get_engine", return_value=engine):
        recorded = await marker(
            {"uid": uid, "aid": AID},
            "retry_exhausted:MapboxTransientError",
        )

    state = await _state_for(engine, uid)
    assert recorded == 1
    assert state is not None
    assert state.status == RouteEnrichmentStatus.failed
    assert state.error_code == "retry_exhausted:MapboxTransientError"


async def test_failed_outcome_fails_workflow() -> None:
    workflow = inspect.unwrap(album_route_enrichment_workflow)
    stats = {
        "candidates": 1,
        "matched": 0,
        "no_route": 0,
        "failed": 1,
        "recorded": 1,
        "updated": 0,
        "route_requests": 1,
        "matching_requests": 1,
        "directions_requests": 0,
        "already_running": False,
    }
    with (
        patch(
            "app.logic.segment_routes.enrich_album_routes_step",
            new=AsyncMock(return_value=stats),
        ),
        pytest.raises(RouteEnrichmentIncompleteError),
    ):
        await workflow({"uid": 1, "aid": AID})


async def test_exhausted_transient_failure_is_recorded_and_propagated() -> None:
    workflow = inspect.unwrap(album_route_enrichment_workflow)
    marker = AsyncMock()
    payload = {"uid": 1, "aid": AID}
    with (
        patch(
            "app.logic.segment_routes.enrich_album_routes_step",
            new=AsyncMock(side_effect=MapboxTransientError("unavailable")),
        ),
        patch(
            "app.logic.segment_routes.mark_album_route_failure_step",
            new=marker,
        ),
        pytest.raises(MapboxTransientError, match="unavailable"),
    ):
        await workflow(payload)

    marker.assert_awaited_once_with(
        payload,
        "retry_exhausted:MapboxTransientError",
    )


async def test_reconciliation_targets_only_unresolved_albums(
    engine: AsyncEngine,
) -> None:
    pending_uid = 3007
    resolved_uid = 3008
    await _seed_segments(
        engine,
        pending_uid,
        (100.0, 200.0, SegmentKind.driving),
        (300.0, 400.0, SegmentKind.walking),
    )
    await _seed_segments(
        engine,
        resolved_uid,
        (100.0, 200.0, SegmentKind.driving),
    )
    await _run_route_enrichment(
        engine,
        resolved_uid,
        route_result=([_no_route()], _stats()),
    )

    async with AsyncSession(engine) as session:
        targets = await pending_route_enrichment_targets(session)

    assert targets.count((pending_uid, AID)) == 1
    assert (resolved_uid, AID) not in targets


async def test_advisory_lock_already_held_skips_run(engine: AsyncEngine) -> None:
    uid = 3009
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))
    result = await _run_route_enrichment(engine, uid, lock_acquired=False)

    result.get_engine.assert_not_called()
    result.match_segments.assert_not_awaited()
    assert result.stats.already_running
    assert await _route_for(engine, uid) is None
