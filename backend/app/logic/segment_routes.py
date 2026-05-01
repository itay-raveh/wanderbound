from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy import String, cast, or_, update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.core.http_clients import HttpClients
from app.core.locks import try_advisory_lock
from app.logic.route_matching import MATCHABLE_KINDS
from app.models.segment import Segment
from app.services.mapbox import match_segments

if TYPE_CHECKING:
    from fastapi import BackgroundTasks
    from sqlalchemy.sql.elements import ColumnElement

logger = logging.getLogger(__name__)

type SegmentKey = tuple[int, str, float, float]
type SegmentSnapshot = tuple[SegmentKey, list[tuple[float, float]], str]


def _route_missing() -> ColumnElement[bool]:
    return or_(col(Segment.route).is_(None), cast(col(Segment.route), String) == "null")


def enqueue_album_route_enrichment(
    background_tasks: BackgroundTasks,
    http: HttpClients,
    uid: int,
    aid: str,
) -> None:
    background_tasks.add_task(match_album_segment_routes, http, uid, aid)


async def match_album_segment_routes(http: HttpClients, uid: int, aid: str) -> None:
    lock_key = f"segment-route-match:{uid}:{aid}"
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
                    return

                pairs = [(coords, profile) for _, coords, profile in snapshots]
                routes = await match_segments(http.mapbox, pairs)

                for (key, _, _), route in zip(snapshots, routes, strict=True):
                    if route:
                        await _write_route(session, key, route)
                await session.commit()
    except Exception:
        logger.exception("Route enrichment failed for uid=%s aid=%s", uid, aid)


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
) -> None:
    uid, aid, start_time, end_time = key
    await session.exec(
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
