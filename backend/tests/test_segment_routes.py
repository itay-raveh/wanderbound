from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.locks import try_advisory_lock
from app.logic.segment_routes import (
    _write_outcome,
    mark_album_route_failure_step,
    match_album_segment_routes,
    pending_route_enrichment_targets,
)
from app.models.polarsteps import Point
from app.models.segment import (
    RouteEnrichmentStatus,
    Segment,
    SegmentKind,
    SegmentRouteEnrichment,
)
from app.services.mapbox import (
    REQUEST_BUDGET_EXCEEDED,
    RouteMatchResult,
)

from .factories import AID, insert_album, insert_segment, make_user

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

type Route = list[tuple[float, float]]
type SegmentSeed = tuple[float, float, SegmentKind]


@pytest.fixture
def engine(
    postgres_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncEngine:
    monkeypatch.setattr("app.logic.segment_routes.get_engine", lambda: postgres_engine)
    monkeypatch.setattr("app.core.locks.get_engine", lambda: postgres_engine)
    return postgres_engine


def _http() -> SimpleNamespace:
    return SimpleNamespace(mapbox_matching=object(), mapbox_directions=object())


def _stats(
    *,
    requests: int = 1,
    matching_requests: int = 1,
    directions_requests: int = 0,
    budget_fallbacks: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        requests=requests,
        matching_requests=matching_requests,
        directions_requests=directions_requests,
        cache_hits=0,
        outbound_attempts=requests,
        retries=0,
        limiter_wait_ms=0,
        provider_latency_ms=0,
        budget_fallbacks=budget_fallbacks,
    )


def _batch(
    *,
    uid: int = 1,
    start_time: float = 100.0,
    end_time: float = 200.0,
) -> list[dict[str, int | str | float]]:
    return [
        {
            "uid": uid,
            "aid": AID,
            "start_time": start_time,
            "end_time": end_time,
        }
    ]


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
        session.add(make_user(uid))
        await session.flush()
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
    route_result: tuple[list[RouteMatchResult], SimpleNamespace] | None = None,
    side_effect: object | None = None,
) -> SimpleNamespace:
    http = http or _http()
    match_segments = AsyncMock(
        side_effect=side_effect,
        return_value=route_result or ([], _stats(requests=0, matching_requests=0)),
    )

    with (
        patch(
            "app.logic.segment_routes.match_segments_with_stats",
            new=match_segments,
        ),
    ):
        stats = await match_album_segment_routes(http, uid, AID)

    return SimpleNamespace(
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

    await _run_route_enrichment(
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


async def test_hike_and_flight_segments_are_skipped(engine: AsyncEngine) -> None:
    uid = 3002
    await _seed_segments(
        engine,
        uid,
        (100.0, 200.0, SegmentKind.hike),
        (300.0, 400.0, SegmentKind.flight),
    )

    await _run_route_enrichment(engine, uid)
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

    await _run_route_enrichment(engine, uid, side_effect=delete_then_match)

    async with AsyncSession(engine) as session:
        assert await session.get(Segment, (uid, AID, 100.0, 200.0)) is None


async def test_no_route_is_recorded_and_not_retried(engine: AsyncEngine) -> None:
    uid = 3004
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))
    await _run_route_enrichment(
        engine,
        uid,
        route_result=([_no_route("NoSegment")], _stats()),
    )

    async def forbidden_provider(*args: object) -> None:
        raise AssertionError("terminal no-route must not charge provider again")

    await _run_route_enrichment(engine, uid, side_effect=forbidden_provider)

    assert await _route_for(engine, uid) is None
    state = await _state_for(engine, uid)
    assert state is not None
    assert state.status == RouteEnrichmentStatus.no_route
    assert state.error_code == "NoSegment"


async def test_request_budget_fallback_is_not_recorded_and_is_retried(
    engine: AsyncEngine,
) -> None:
    uid = 3011
    route = [(4.0, 52.0), (4.1, 52.1)]
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))

    await _run_route_enrichment(
        engine,
        uid,
        route_result=(
            [_no_route(REQUEST_BUDGET_EXCEEDED)],
            _stats(
                requests=0,
                matching_requests=0,
                budget_fallbacks=1,
            ),
        ),
    )

    assert await _state_for(engine, uid) is None

    await _run_route_enrichment(
        engine,
        uid,
        route_result=([_matched(route)], _stats()),
    )

    assert await _route_for(engine, uid) == route
    state = await _state_for(engine, uid)
    assert state is not None
    assert state.status == RouteEnrichmentStatus.matched


async def test_permanent_failure_is_recorded(engine: AsyncEngine) -> None:
    uid = 3005
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))
    await _run_route_enrichment(
        engine,
        uid,
        route_result=([_failed()], _stats()),
    )

    state = await _state_for(engine, uid)
    assert state is not None
    assert state.status == RouteEnrichmentStatus.failed
    assert state.error_code == "InvalidInput"


async def test_route_matching_exception_propagates(engine: AsyncEngine) -> None:
    uid = 3006
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))

    with pytest.raises(RuntimeError, match="mapbox unavailable"):
        await _run_route_enrichment(
            engine,
            uid,
            side_effect=RuntimeError("mapbox unavailable"),
        )


async def test_exhausted_failure_marker_records_only_attempted_batch(
    engine: AsyncEngine,
) -> None:
    uid = 3010
    await _seed_segments(
        engine,
        uid,
        (100.0, 200.0, SegmentKind.driving),
        (300.0, 400.0, SegmentKind.driving),
    )
    marker = inspect.unwrap(mark_album_route_failure_step)

    with patch("app.logic.segment_routes.get_engine", return_value=engine):
        recorded = await marker(
            {"uid": uid, "aid": AID},
            "retry_exhausted:MapboxTransientError",
            _batch(uid=uid),
        )

    state = await _state_for(engine, uid)
    unattempted_state = await _state_for(
        engine,
        uid,
        start_time=300.0,
        end_time=400.0,
    )
    assert recorded == 1
    assert state is not None
    assert state.status == RouteEnrichmentStatus.failed
    assert state.error_code == "retry_exhausted:MapboxTransientError"
    assert unattempted_state is None


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
    async with try_advisory_lock(f"segment-route-match:{uid}:{AID}") as acquired:
        assert acquired

        async def forbidden_provider(*args: object) -> None:
            raise AssertionError("competing route run must not charge provider")

        await _run_route_enrichment(engine, uid, side_effect=forbidden_provider)
        assert await _route_for(engine, uid) is None
    await _run_route_enrichment(
        engine, uid, route_result=([_matched([(4, 52), (5, 53)])], _stats())
    )
    assert await _route_for(engine, uid) == [(4, 52), (5, 53)]


@pytest.mark.parametrize("saved_route", [[], [(4.2, 52.2)]])
@pytest.mark.parametrize("repaired", [False, True])
async def test_stale_success_is_repaired_once_without_retrying_terminal_failure(
    engine: AsyncEngine, saved_route: Route, *, repaired: bool
) -> None:
    uid = 3991 + int(repaired) * 4 + int(bool(saved_route)) * 2
    terminal_uid = uid + 1
    coords = [(4.0, 52.0), (4.1, 52.1), (4.2, 52.2)]
    points = [Point(lon=x, lat=y, time=100 + i * 50) for i, (x, y) in enumerate(coords)]
    async with AsyncSession(engine) as session:
        for owner in (uid, terminal_uid):
            session.add(make_user(owner))
            await session.flush()
            await insert_album(session, owner)
            segment = await insert_segment(
                session, owner, start_time=100, end_time=200, points=points
            )
            segment.route = saved_route if owner == uid else None
            session.add(segment)
            session.add(
                SegmentRouteEnrichment(
                    uid=owner,
                    aid=AID,
                    start_time=100,
                    end_time=200,
                    status=RouteEnrichmentStatus.matched
                    if owner == uid
                    else RouteEnrichmentStatus.no_route,
                    error_code=None if owner == uid else "NoSegment",
                )
            )
        await session.commit()
        targets = await pending_route_enrichment_targets(session)
    assert (uid, AID) in targets
    assert (terminal_uid, AID) not in targets

    outcome = _matched(coords) if repaired else _no_route("incomplete_match")
    await _run_route_enrichment(engine, uid, route_result=([outcome], _stats()))
    assert await _route_for(engine, uid) == (coords if repaired else None)
    state = await _state_for(engine, uid)
    assert state is not None
    assert state.status == outcome.status
    assert state.error_code == outcome.error_code
    async with AsyncSession(engine) as session:
        assert (uid, AID) not in await pending_route_enrichment_targets(session)
    terminal = await _state_for(engine, terminal_uid)
    assert terminal is not None
    assert terminal.error_code == "NoSegment"
    assert await _route_for(engine, terminal_uid) is None


async def test_changed_gps_during_matching_never_receives_stale_route(
    engine: AsyncEngine,
) -> None:
    uid = 4100
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))
    new_points = [Point(lon=10, lat=50, time=100), Point(lon=11, lat=51, time=200)]

    async def change_then_match(
        *_args: object,
    ) -> tuple[list[RouteMatchResult], SimpleNamespace]:
        async with AsyncSession(engine) as session:
            segment = await session.get(Segment, (uid, AID, 100.0, 200.0))
            assert segment is not None
            segment.points = new_points
            session.add(segment)
            await session.commit()
        return [_matched([(4, 52), (5, 53)])], _stats()

    await _run_route_enrichment(engine, uid, side_effect=change_then_match)
    assert await _route_for(engine, uid) is None
    assert await _state_for(engine, uid) is None
    async with AsyncSession(engine) as session:
        segment = await session.get(Segment, (uid, AID, 100.0, 200.0))
        assert segment is not None
        assert segment.points == new_points


async def test_single_point_match_is_terminal_without_repeated_paid_repair(
    engine: AsyncEngine,
) -> None:
    uid = 4101
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))
    await _run_route_enrichment(
        engine, uid, route_result=([_matched([(4, 52)])], _stats())
    )
    assert await _route_for(engine, uid) is None
    state = await _state_for(engine, uid)
    assert state is not None
    assert state.status == RouteEnrichmentStatus.failed
    assert state.error_code == "invalid_geometry"
    await _run_route_enrichment(
        engine,
        uid,
        side_effect=AssertionError(
            "terminal geometry must not incur another paid request"
        ),
    )


async def test_startup_recovery_does_not_deserialize_unrelated_history(
    engine: AsyncEngine,
) -> None:
    historical_uid, pending_uid = 4102, 4103
    await _seed_segments(engine, historical_uid, (100.0, 200.0, SegmentKind.driving))
    await _run_route_enrichment(
        engine, historical_uid, route_result=([_matched([(4, 52), (5, 53)])], _stats())
    )
    await _seed_segments(engine, pending_uid, (100.0, 200.0, SegmentKind.driving))
    # Incompatible historical GPS cannot block startup recovery for another user.
    # Startup needs album keys, never historical Point model deserialization.
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE segment SET points = :points WHERE uid = :uid"),
            {"points": '[{"legacy_coordinate": 1}]', "uid": historical_uid},
        )
    try:
        async with AsyncSession(engine) as session:
            targets = await pending_route_enrichment_targets(session)
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE segment SET points = :points WHERE uid = :uid"),
                {"points": "[]", "uid": historical_uid},
            )
    assert (pending_uid, AID) in targets
    assert (historical_uid, AID) not in targets


async def test_ambiguous_legacy_route_is_preserved_without_paid_repair(
    engine: AsyncEngine,
) -> None:
    uid = 4104
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))
    async with AsyncSession(engine) as session:
        segment = await session.get(Segment, (uid, AID, 100.0, 200.0))
        assert segment is not None
        segment.points = [
            Point(lon=4, lat=52, time=100),
            Point(lon=4.1, lat=52.1, time=150),
            Point(lon=4.2, lat=52.2, time=200),
        ]
        session.add(segment)
        await session.commit()
    route = [(30.0, 20.0), (30.1, 20.1)]
    await _run_route_enrichment(engine, uid, route_result=([_matched(route)], _stats()))
    await _run_route_enrichment(
        engine,
        uid,
        side_effect=AssertionError("legacy geometry is not proof of corruption"),
    )
    assert await _route_for(engine, uid) == route


async def test_older_failure_cannot_clear_concurrently_committed_repair(
    engine: AsyncEngine,
) -> None:
    uid = 4105
    key = (uid, AID, 100.0, 200.0)
    await _seed_segments(engine, uid, (100.0, 200.0, SegmentKind.driving))
    route = [(4.0, 52.0), (4.1, 52.1)]
    async with AsyncSession(engine, expire_on_commit=False) as older:
        cached_segment = await older.get(Segment, key)
        assert cached_segment is not None
        coords = [(p.lon, p.lat, p.time) for p in cached_segment.points]
        # Hold the old identity-map object while another transaction repairs it.
        async with AsyncSession(engine) as repair:
            await _write_outcome(repair, key, _matched(route), coords, "driving")
            await repair.commit()
        await _write_outcome(older, key, _failed("older_failure"), coords, "driving")
        await older.commit()
    assert await _route_for(engine, uid) == route
    state = await _state_for(engine, uid)
    assert state is not None
    assert state.status == RouteEnrichmentStatus.matched
