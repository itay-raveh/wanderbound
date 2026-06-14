from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
from dbos import DBOS, SetWorkflowID
from sqlalchemy import String, cast, or_, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.core.http_clients import HttpClients
from app.core.locks import try_advisory_lock
from app.core.observability import set_span_data, start_span
from app.logic.route_matching import MATCHABLE_KINDS
from app.models.segment import Segment
from app.services.mapbox import match_segments_with_stats

if TYPE_CHECKING:
    from fastapi import BackgroundTasks
    from sentry_sdk.tracing import Span
    from sqlalchemy.sql.elements import ColumnElement

logger = structlog.get_logger(__name__)

type SegmentKey = tuple[int, str, float, float]
type SegmentSnapshot = tuple[SegmentKey, list[tuple[float, float]], str]

_route_http_clients: list[HttpClients] = []


@dataclass
class RouteEnrichmentStats:
    candidates: int = 0
    matched: int = 0
    updated: int = 0
    route_requests: int = 0
    matching_requests: int = 0
    directions_requests: int = 0

    @property
    def skipped(self) -> int:
        return self.candidates - self.matched

    @property
    def stale(self) -> int:
        return self.matched - self.updated


def _route_missing() -> ColumnElement[bool]:
    return or_(col(Segment.route).is_(None), cast(col(Segment.route), String) == "null")


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


@DBOS.workflow(name="route.enrich_album")
async def album_route_enrichment_workflow(payload: dict[str, Any]) -> dict[str, Any]:
    uid = int(payload["uid"])
    aid = str(payload["aid"])
    await match_album_segment_routes(get_route_enrichment_http_clients(), uid, aid)
    return route_enrichment_payload(uid, aid)


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


async def match_album_segment_routes(http: HttpClients, uid: int, aid: str) -> None:
    lock_key = f"segment-route-match:{uid}:{aid}"
    started = time.perf_counter()
    try:
        with start_span(
            "route_enrichment.run",
            "Run route enrichment",
            **{"app.workflow": "route_enrichment", "user.id": uid, "album.id": aid},
        ) as span:
            async with try_advisory_lock(lock_key) as acquired:
                if not acquired:
                    set_span_data(span, result="already_running")
                    logger.info(
                        "route_enrichment.already_running",
                        user_id=uid,
                        album_id=aid,
                    )
                    return

                async with AsyncSession(get_engine()) as session:
                    snapshots = await _unmatched_snapshots(session, uid, aid)
                    if not snapshots:
                        stats = RouteEnrichmentStats()
                        _set_route_span_data(span, stats, result="empty")
                        _log_complete(uid, aid, started, stats)
                        return

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
                        routes, route_stats = await match_segments_with_stats(
                            http.mapbox_matching,
                            http.mapbox_directions,
                            pairs,
                        )

                    stats = RouteEnrichmentStats(candidates=len(snapshots))
                    stats.route_requests = route_stats.requests
                    stats.matching_requests = route_stats.matching_requests
                    stats.directions_requests = route_stats.directions_requests
                    for (key, _, _), route in zip(snapshots, routes, strict=True):
                        if route:
                            stats.matched += 1
                            stats.updated += await _write_route(session, key, route)
                    await session.commit()
                    _set_route_span_data(span, stats, result="completed")
                    _log_complete(uid, aid, started, stats)
    except Exception:
        logger.exception(
            "route_enrichment.failed",
            user_id=uid,
            album_id=aid,
            duration_ms=_duration_ms(started),
        )


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
            "route.updated": stats.updated,
            "route.skipped": stats.skipped,
            "route.stale": stats.stale,
            "route.requests": stats.route_requests,
            "mapbox.matching_requests": stats.matching_requests,
            "mapbox.directions_requests": stats.directions_requests,
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
        updated=stats.updated,
        skipped=stats.skipped,
        stale=stats.stale,
        route_requests=stats.route_requests,
        matching_requests=stats.matching_requests,
        directions_requests=stats.directions_requests,
        duration_ms=_duration_ms(started),
    )


async def _unmatched_snapshots(
    session: AsyncSession, uid: int, aid: str
) -> list[SegmentSnapshot]:
    result = await session.exec(
        select(Segment)
        .where(
            Segment.uid == uid,
            Segment.aid == aid,
            col(Segment.kind).in_(MATCHABLE_KINDS),
            _route_missing(),
        )
        .order_by(col(Segment.start_time))
    )
    return [
        (
            (seg.uid, seg.aid, seg.start_time, seg.end_time),
            [(p.lon, p.lat) for p in seg.points],
            str(seg.kind),
        )
        for seg in result.all()
    ]


async def _write_route(
    session: AsyncSession,
    key: SegmentKey,
    route: Sequence[tuple[float, float]],
) -> int:
    uid, aid, start_time, end_time = key
    result = await session.exec(
        update(Segment)
        .where(
            col(Segment.uid) == uid,
            col(Segment.aid) == aid,
            col(Segment.start_time) == start_time,
            col(Segment.end_time) == end_time,
            _route_missing(),
        )
        .values(route=list(route))
    )
    return result.rowcount or 0
