from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
from dbos import DBOS, SetWorkflowID
from sqlalchemy import String, and_, cast, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.core.http_clients import HttpClients
from app.core.locks import try_advisory_lock
from app.core.observability import set_span_data, start_span
from app.logic.route_matching import MATCHABLE_KINDS
from app.models.segment import (
    RouteEnrichmentStatus,
    Segment,
    SegmentRouteEnrichment,
)
from app.services.mapbox import (
    REQUEST_BUDGET_EXCEEDED,
    RouteMatchResult,
    match_segments_with_stats,
    route_request_batch_indices,
)

if TYPE_CHECKING:
    from fastapi import BackgroundTasks
    from sentry_sdk.tracing import Span
    from sqlalchemy.sql.elements import ColumnElement

logger = structlog.get_logger(__name__)

type SegmentKey = tuple[int, str, float, float]
type SegmentKeyPayload = dict[str, int | str | float]
type SegmentSnapshot = tuple[SegmentKey, list[tuple[float, float, float]], str]

_route_http_clients: list[HttpClients] = []


class RouteEnrichmentIncompleteError(RuntimeError):
    pass


@dataclass
class RouteEnrichmentStats:
    candidates: int = 0
    matched: int = 0
    no_route: int = 0
    failed: int = 0
    recorded: int = 0
    updated: int = 0
    route_requests: int = 0
    matching_requests: int = 0
    directions_requests: int = 0
    cache_hits: int = 0
    outbound_attempts: int = 0
    retries: int = 0
    limiter_wait_ms: int = 0
    provider_latency_ms: int = 0
    budget_fallbacks: int = 0
    already_running: bool = False

    @property
    def stale(self) -> int:
        return self.candidates - self.recorded


def _segment_key_payload(key: SegmentKey) -> SegmentKeyPayload:
    uid, aid, start_time, end_time = key
    return {
        "uid": uid,
        "aid": aid,
        "start_time": start_time,
        "end_time": end_time,
    }


def _segment_key_from_payload(payload: SegmentKeyPayload) -> SegmentKey:
    return (
        int(payload["uid"]),
        str(payload["aid"]),
        float(payload["start_time"]),
        float(payload["end_time"]),
    )


def _snapshots_for_keys(
    snapshots: list[SegmentSnapshot],
    keys: list[SegmentKey] | None,
) -> list[SegmentSnapshot]:
    if keys is None:
        return snapshots
    by_key = {snapshot[0]: snapshot for snapshot in snapshots}
    return [by_key[key] for key in keys if key in by_key]


def _route_missing() -> ColumnElement[bool]:
    return or_(col(Segment.route).is_(None), cast(col(Segment.route), String) == "null")


def _without_enrichment_state() -> ColumnElement[bool]:
    return col(SegmentRouteEnrichment.uid).is_(None)


def _enrichment_join() -> ColumnElement[bool]:
    return and_(
        col(SegmentRouteEnrichment.uid) == col(Segment.uid),
        col(SegmentRouteEnrichment.aid) == col(Segment.aid),
        col(SegmentRouteEnrichment.start_time) == col(Segment.start_time),
        col(SegmentRouteEnrichment.end_time) == col(Segment.end_time),
    )


def enqueue_album_route_enrichment(
    background_tasks: BackgroundTasks,
    http: HttpClients,
    uid: int,
    aid: str,
) -> None:
    background_tasks.add_task(start_album_route_enrichment, uid, aid)


def schedule_album_route_enrichment(http: HttpClients, uid: int, aid: str) -> None:
    start_album_route_enrichment(uid, aid)


def set_route_enrichment_http_clients(http: HttpClients | None) -> None:
    _route_http_clients.clear()
    if http is not None:
        _route_http_clients.append(http)


def get_route_enrichment_http_clients() -> HttpClients:
    if not _route_http_clients:
        msg = "route enrichment HTTP clients have not been initialized"
        raise RuntimeError(msg)
    return _route_http_clients[0]


def route_enrichment_workflow_id(uid: int, aid: str) -> str:
    return f"route-enrichment:{uid}:{aid}:{uuid4().hex}"


def route_enrichment_payload(uid: int, aid: str) -> dict[str, Any]:
    return {"uid": uid, "aid": aid}


@DBOS.step(retries_allowed=True, max_attempts=3)
async def plan_album_route_batch_step(
    payload: dict[str, Any],
) -> list[SegmentKeyPayload]:
    uid = int(payload["uid"])
    aid = str(payload["aid"])
    async with AsyncSession(get_engine()) as session:
        snapshots = await _unmatched_snapshots(session, uid, aid)
    pairs = [(coords, profile) for _, coords, profile in snapshots]
    indexes = route_request_batch_indices(pairs)
    if snapshots and not indexes:
        msg = "no route enrichment candidate fits the request budget"
        raise RouteEnrichmentIncompleteError(msg)
    return [_segment_key_payload(snapshots[index][0]) for index in indexes]


@DBOS.step(
    retries_allowed=True,
    max_attempts=3,
    interval_seconds=5,
    backoff_rate=2,
)
async def enrich_album_routes_step(
    payload: dict[str, Any], batch: list[SegmentKeyPayload]
) -> dict[str, Any]:
    uid = int(payload["uid"])
    aid = str(payload["aid"])
    stats = await match_album_segment_routes(
        get_route_enrichment_http_clients(),
        uid,
        aid,
        [_segment_key_from_payload(key) for key in batch],
    )
    return asdict(stats)


@DBOS.step(retries_allowed=True, max_attempts=3)
async def mark_album_route_failure_step(
    payload: dict[str, Any],
    error_code: str,
    batch: list[SegmentKeyPayload],
) -> int:
    uid = int(payload["uid"])
    aid = str(payload["aid"])
    async with AsyncSession(get_engine()) as session:
        return await _mark_pending_failed(
            session,
            uid,
            aid,
            error_code,
            [_segment_key_from_payload(key) for key in batch],
        )


@DBOS.workflow(name="route.enrich_album")
async def album_route_enrichment_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    failed = 0
    while batch := await plan_album_route_batch_step(payload):
        try:
            result = await enrich_album_routes_step(payload, batch)
        except Exception as exc:
            error_code = f"retry_exhausted:{type(exc).__name__}"
            try:
                await mark_album_route_failure_step(payload, error_code, batch)
            except Exception as marker_exc:
                logger.exception(
                    "route_enrichment.failure_record_failed",
                    user_id=int(payload["uid"]),
                    album_id=str(payload["aid"]),
                    error_type=type(marker_exc).__name__,
                )
            raise

        stats = RouteEnrichmentStats(**result)
        if stats.already_running:
            break
        if stats.budget_fallbacks:
            msg = "route enrichment batch exceeded its planned request budget"
            raise RouteEnrichmentIncompleteError(msg)
        failed += stats.failed

    if failed:
        msg = f"route enrichment recorded {failed} failed segment(s)"
        raise RouteEnrichmentIncompleteError(msg)
    return route_enrichment_payload(int(payload["uid"]), str(payload["aid"]))


def start_album_route_enrichment(uid: int, aid: str) -> object:
    try:
        with SetWorkflowID(route_enrichment_workflow_id(uid, aid)):
            return DBOS.start_workflow(
                album_route_enrichment_workflow,
                route_enrichment_payload(uid, aid),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "route_enrichment.schedule_failed",
            user_id=uid,
            album_id=aid,
            error_type=type(exc).__name__,
        )
        return None


async def pending_route_enrichment_targets(
    session: AsyncSession,
) -> list[tuple[int, str]]:
    rows = await session.exec(
        select(Segment.uid, Segment.aid)
        .outerjoin(SegmentRouteEnrichment, _enrichment_join())
        .where(
            col(Segment.kind).in_(MATCHABLE_KINDS),
            _route_missing(),
            _without_enrichment_state(),
        )
        .distinct()
        .order_by(col(Segment.uid), col(Segment.aid))
    )
    return list(rows.all())


async def reconcile_missing_route_enrichments() -> None:
    async with AsyncSession(get_engine()) as session:
        targets = await pending_route_enrichment_targets(session)
    for uid, aid in targets:
        start_album_route_enrichment(uid, aid)


async def match_album_segment_routes(
    http: HttpClients,
    uid: int,
    aid: str,
    keys: list[SegmentKey] | None = None,
) -> RouteEnrichmentStats:
    lock_key = f"segment-route-match:{uid}:{aid}"
    started = time.perf_counter()
    with start_span(
        "route_enrichment.run",
        "Run route enrichment",
        **{"app.workflow": "route_enrichment", "user.id": uid, "album.id": aid},
    ) as span:
        async with try_advisory_lock(lock_key) as acquired:
            if not acquired:
                stats = RouteEnrichmentStats(already_running=True)
                set_span_data(span, result="already_running")
                logger.info(
                    "route_enrichment.already_running",
                    user_id=uid,
                    album_id=aid,
                )
                return stats

            try:
                async with AsyncSession(get_engine()) as session:
                    return await _match_routes_in_session(
                        http, session, uid, aid, span, started, keys
                    )
            except Exception:
                logger.exception(
                    "route_enrichment.failed",
                    user_id=uid,
                    album_id=aid,
                    duration_ms=_duration_ms(started),
                )
                raise


async def _match_routes_in_session(  # noqa: PLR0913
    http: HttpClients,
    session: AsyncSession,
    uid: int,
    aid: str,
    span: Span,
    started: float,
    keys: list[SegmentKey] | None,
) -> RouteEnrichmentStats:
    snapshots = _snapshots_for_keys(
        await _unmatched_snapshots(session, uid, aid),
        keys,
    )
    if not snapshots:
        stats = RouteEnrichmentStats()
        _set_route_span_data(span, stats, result="empty")
        _log_complete(uid, aid, started, stats)
        return stats

    pairs = [(coords, profile) for _, coords, profile in snapshots]
    with start_span(
        "route_enrichment.match",
        "Match segment routes",
        **{
            "app.workflow": "route_enrichment",
            "user.id": uid,
            "album.id": aid,
            "route.candidates": len(snapshots),
        },
    ):
        results, route_stats = await match_segments_with_stats(
            http.mapbox_matching,
            http.mapbox_directions,
            pairs,
        )

    stats = RouteEnrichmentStats(candidates=len(snapshots))
    stats.route_requests = route_stats.requests
    stats.matching_requests = route_stats.matching_requests
    stats.directions_requests = route_stats.directions_requests
    stats.cache_hits = route_stats.cache_hits
    stats.outbound_attempts = route_stats.outbound_attempts
    stats.retries = route_stats.retries
    stats.limiter_wait_ms = route_stats.limiter_wait_ms
    stats.provider_latency_ms = route_stats.provider_latency_ms
    stats.budget_fallbacks = route_stats.budget_fallbacks
    for (key, _, _), result in zip(snapshots, results, strict=True):
        outcome = result
        if outcome.error_code == REQUEST_BUDGET_EXCEEDED:
            continue
        if outcome.status == RouteEnrichmentStatus.matched and not outcome.route:
            outcome = RouteMatchResult(
                status=RouteEnrichmentStatus.failed,
                error_code="invalid_geometry",
            )
        if outcome.status == RouteEnrichmentStatus.matched:
            stats.matched += 1
        elif outcome.status == RouteEnrichmentStatus.no_route:
            stats.no_route += 1
        else:
            stats.failed += 1
        recorded, updated = await _write_outcome(session, key, outcome)
        stats.recorded += recorded
        stats.updated += updated
    await session.commit()
    _set_route_span_data(span, stats, result="completed")
    _log_complete(uid, aid, started, stats)
    return stats


def _duration_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _set_route_span_data(
    span: Span,
    stats: RouteEnrichmentStats,
    *,
    result: str,
) -> None:
    set_span_data(
        span,
        result=result,
        **{
            "route.candidates": stats.candidates,
            "route.matched": stats.matched,
            "route.no_route": stats.no_route,
            "route.failed": stats.failed,
            "route.recorded": stats.recorded,
            "route.updated": stats.updated,
            "route.stale": stats.stale,
            "route.requests": stats.route_requests,
            "mapbox.matching_requests": stats.matching_requests,
            "mapbox.directions_requests": stats.directions_requests,
            "mapbox.cache_hits": stats.cache_hits,
            "mapbox.outbound_attempts": stats.outbound_attempts,
            "mapbox.retries": stats.retries,
            "mapbox.limiter_wait_ms": stats.limiter_wait_ms,
            "mapbox.provider_latency_ms": stats.provider_latency_ms,
            "mapbox.budget_fallbacks": stats.budget_fallbacks,
        },
    )


def _log_complete(
    uid: int,
    aid: str,
    started: float,
    stats: RouteEnrichmentStats,
) -> None:
    logger.info(
        "route_enrichment.completed",
        user_id=uid,
        album_id=aid,
        candidates=stats.candidates,
        matched=stats.matched,
        no_route=stats.no_route,
        failed=stats.failed,
        recorded=stats.recorded,
        updated=stats.updated,
        stale=stats.stale,
        route_requests=stats.route_requests,
        matching_requests=stats.matching_requests,
        directions_requests=stats.directions_requests,
        cache_hits=stats.cache_hits,
        outbound_attempts=stats.outbound_attempts,
        retries=stats.retries,
        limiter_wait_ms=stats.limiter_wait_ms,
        provider_latency_ms=stats.provider_latency_ms,
        budget_fallbacks=stats.budget_fallbacks,
        duration_ms=_duration_ms(started),
    )


async def _unmatched_snapshots(
    session: AsyncSession, uid: int, aid: str
) -> list[SegmentSnapshot]:
    result = await session.exec(
        select(Segment)
        .outerjoin(SegmentRouteEnrichment, _enrichment_join())
        .where(
            Segment.uid == uid,
            Segment.aid == aid,
            col(Segment.kind).in_(MATCHABLE_KINDS),
            _route_missing(),
            _without_enrichment_state(),
        )
        .order_by(col(Segment.start_time))
    )
    return [
        (
            (seg.uid, seg.aid, seg.start_time, seg.end_time),
            [(p.lon, p.lat, p.time) for p in seg.points],
            str(seg.kind),
        )
        for seg in result.all()
    ]


async def _write_outcome(
    session: AsyncSession,
    key: SegmentKey,
    result: RouteMatchResult,
) -> tuple[int, int]:
    segment = await session.get(Segment, key)
    state = await session.get(SegmentRouteEnrichment, key)
    if segment is None or segment.route is not None or state is not None:
        return 0, 0

    updated = 0
    if result.status == RouteEnrichmentStatus.matched and result.route:
        segment.route = list(result.route)
        session.add(segment)
        updated = 1

    session.add(
        SegmentRouteEnrichment(
            uid=segment.uid,
            aid=segment.aid,
            start_time=segment.start_time,
            end_time=segment.end_time,
            status=result.status,
            error_code=result.error_code,
        )
    )
    return 1, updated


async def _mark_pending_failed(
    session: AsyncSession,
    uid: int,
    aid: str,
    error_code: str,
    keys: list[SegmentKey],
) -> int:
    snapshots = _snapshots_for_keys(
        await _unmatched_snapshots(session, uid, aid),
        keys,
    )
    failed = RouteMatchResult(
        status=RouteEnrichmentStatus.failed,
        error_code=error_code[:100],
    )
    recorded = 0
    for key, _, _ in snapshots:
        wrote, _ = await _write_outcome(session, key, failed)
        recorded += wrote
    await session.commit()
    return recorded
