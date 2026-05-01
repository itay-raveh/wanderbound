from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import String, cast, or_, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.core.http_clients import HttpClients
from app.core.locks import try_advisory_lock
from app.logic.route_matching import MATCHABLE_KINDS
from app.models.segment import Segment
from app.services.mapbox import match_segments_with_stats

if TYPE_CHECKING:
    from fastapi import BackgroundTasks
    from sqlalchemy.sql.elements import ColumnElement

logger = logging.getLogger(__name__)

type SegmentKey = tuple[int, str, float, float]
type SegmentSnapshot = tuple[SegmentKey, list[tuple[float, float]], str]

_route_tasks: set[asyncio.Task[None]] = set()


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
    background_tasks.add_task(match_album_segment_routes, http, uid, aid)


def schedule_album_route_enrichment(http: HttpClients, uid: int, aid: str) -> None:
    task = asyncio.create_task(match_album_segment_routes(http, uid, aid))
    _route_tasks.add(task)
    task.add_done_callback(_route_tasks.discard)


async def match_album_segment_routes(http: HttpClients, uid: int, aid: str) -> None:
    lock_key = f"segment-route-match:{uid}:{aid}"
    started = time.perf_counter()
    try:
        async with try_advisory_lock(lock_key) as acquired:
            if not acquired:
                logger.info(
                    "Route enrichment already running for uid=%s aid=%s", uid, aid
                )
                return

            async with AsyncSession(get_engine()) as session:
                snapshots = await _unmatched_snapshots(session, uid, aid)
                if not snapshots:
                    _log_complete(uid, aid, started, RouteEnrichmentStats())
                    return

                pairs = [(coords, profile) for _, coords, profile in snapshots]
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
                _log_complete(uid, aid, started, stats)
    except Exception:
        logger.exception(
            "Route enrichment failed for uid=%s aid=%s duration_ms=%d",
            uid,
            aid,
            _duration_ms(started),
        )


def _duration_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _log_complete(
    uid: int,
    aid: str,
    started: float,
    stats: RouteEnrichmentStats,
) -> None:
    logger.info(
        "Route enrichment complete uid=%s aid=%s candidates=%d matched=%d "
        "updated=%d skipped=%d stale=%d route_requests=%d "
        "matching_requests=%d directions_requests=%d duration_ms=%d",
        uid,
        aid,
        stats.candidates,
        stats.matched,
        stats.updated,
        stats.skipped,
        stats.stale,
        stats.route_requests,
        stats.matching_requests,
        stats.directions_requests,
        _duration_ms(started),
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
