import logging
from collections.abc import AsyncIterable, Sequence
from math import atan2, cos, radians, sin, sqrt
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
    status,
)
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse
from sqlmodel import select

from app.logic.layout.media import Media
from app.logic.matching import MATCHABLE_KINDS, match_segment
from app.logic.pdf import PdfEvent, pop_pdf_token, render_album_pdf_stream
from app.models.album import Album, AlbumMeta, AlbumUpdate, PrintBundle
from app.models.segment import (
    BoundaryAdjust,
    Segment,
    SegmentKind,
    SegmentOutline,
    split_segments,
)
from app.models.step import Step, StepUpdate

from ..deps import BrowserDep, SessionDep, UserDep

logger = logging.getLogger(__name__)


async def _get_album(
    aid: Annotated[str, Path()], user: UserDep, session: SessionDep
) -> Album:
    return await session.get_one(Album, (user.id, aid))


AlbumDep = Annotated[Album, Depends(_get_album)]

router = APIRouter(prefix="/albums", tags=["albums"])


# Static-prefix routes must be declared before /{aid} to avoid shadowing.
@router.get("/pdf/download/{token}")
async def download_pdf(
    token: str,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    result = pop_pdf_token(token)
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Invalid or expired token"
        )
    path, aid = result
    background_tasks.add_task(path.unlink, missing_ok=True)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{aid}.pdf",
    )


@router.get("/{aid}")
async def read_album(aid: str, album: AlbumDep) -> AlbumMeta:
    return AlbumMeta.model_validate(album)


@router.get("/{aid}/media")
async def read_media(aid: str, album: AlbumDep) -> list[Media]:
    return album.media


@router.get("/{aid}/steps")
async def read_steps(aid: str, user: UserDep, session: SessionDep) -> list[Step]:
    result = await session.exec(
        select(Step)
        .where(Step.uid == user.id, Step.aid == aid)
        .order_by(Step.timestamp, Step.id)  # type: ignore[union-attr]
    )
    return list(result.all())


@router.get("/{aid}/segments")
async def read_segments(
    aid: str, user: UserDep, session: SessionDep
) -> list[SegmentOutline]:
    result = await session.exec(
        select(Segment)
        .where(Segment.uid == user.id, Segment.aid == aid)
        .order_by(Segment.start_time)  # type: ignore[union-attr]
    )
    return [SegmentOutline.from_segment(s) for s in result.all()]


@router.get("/{aid}/segments/points")
async def read_segment_points(
    aid: str,
    user: UserDep,
    session: SessionDep,
    from_time: Annotated[float, Query()],
    to_time: Annotated[float, Query()],
) -> Sequence[Segment]:
    result = await session.exec(
        select(Segment)
        .where(
            Segment.uid == user.id,
            Segment.aid == aid,
            Segment.start_time >= from_time,
            Segment.end_time <= to_time,
        )
        .order_by(Segment.start_time)  # type: ignore[union-attr]
    )
    segments = result.all()

    # Auto-match driving/walking segments that don't have a route yet
    for seg in segments:
        if seg.kind in MATCHABLE_KINDS and seg.route is None:
            profile = "driving" if seg.kind == SegmentKind.driving else "walking"
            coords_lonlat = [(p.lon, p.lat) for p in seg.points]
            route = await match_segment(coords_lonlat, profile)
            if route:
                seg.route = route
                session.add(seg)
    await session.commit()

    return segments


@router.patch("/{aid}")
async def update_album(
    aid: str,
    update: AlbumUpdate,
    album: AlbumDep,
    session: SessionDep,
) -> AlbumMeta:
    album.sqlmodel_update(update.model_dump(exclude_unset=True))
    session.add(album)
    await session.commit()
    await session.refresh(album)
    return AlbumMeta.model_validate(album)


@router.patch("/{aid}/steps/{sid}")
async def update_step(
    aid: str,
    sid: int,
    update: StepUpdate,
    user: UserDep,
    session: SessionDep,
) -> Step:
    step: Step = await session.get_one(Step, (user.id, aid, sid))
    step.sqlmodel_update(update.model_dump(exclude_unset=True))
    session.add(step)
    await session.commit()
    await session.refresh(step)
    return step


@router.patch("/{aid}/segments/adjust-boundary")
async def adjust_segment_boundary(
    aid: str,
    body: BoundaryAdjust,
    user: UserDep,
    session: SessionDep,
) -> list[SegmentOutline]:
    uid = user.id

    # Lock the target segment for the duration of this transaction
    target = await session.get(
        Segment, (uid, aid, body.start_time, body.end_time), with_for_update=True
    )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Segment not found")

    if target.kind == SegmentKind.flight:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Cannot adjust boundary of a flight segment",
        )

    # Find the adjacent segment (nearest non-overlapping on the relevant side)
    if body.handle == "start":
        time_filter = Segment.end_time <= target.start_time
        ordering = Segment.end_time.desc()  # type: ignore[union-attr]
    else:
        time_filter = Segment.start_time >= target.end_time
        ordering = Segment.start_time.asc()  # type: ignore[union-attr]
    result = await session.exec(
        select(Segment)
        .where(
            Segment.uid == uid,
            Segment.aid == aid,
            Segment.kind != SegmentKind.flight,
            time_filter,
        )
        .order_by(ordering)
        .limit(1)
        .with_for_update()
    )
    adjacent = result.first()
    if adjacent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No adjacent segment")

    try:
        new_earlier, new_later = split_segments(
            target,
            adjacent,
            body.new_boundary_time,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    await session.delete(target)
    await session.delete(adjacent)
    # Flush deletes first to avoid composite PK collision with new segments
    await session.flush()
    session.add(new_earlier)
    session.add(new_later)
    await session.commit()

    logger.info(
        "Adjusted segment boundary",
        extra={"uid": uid, "aid": aid, "handle": body.handle},
    )

    result = await session.exec(
        select(Segment)
        .where(Segment.uid == uid, Segment.aid == aid)
        .order_by(Segment.start_time)  # type: ignore[union-attr]
    )
    return [SegmentOutline.from_segment(s) for s in result.all()]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))


def _total_distance_km(segments: list[Segment]) -> float:
    total = 0.0
    for seg in segments:
        for i in range(len(seg.points) - 1):
            total += _haversine_km(
                seg.points[i].lat,
                seg.points[i].lon,
                seg.points[i + 1].lat,
                seg.points[i + 1].lon,
            )
    return round(total, 1)


@router.get("/{aid}/print-bundle")
async def read_print_bundle(
    aid: str, user: UserDep, session: SessionDep
) -> PrintBundle:
    album = await session.get_one(Album, (user.id, aid))
    steps_result = await session.exec(
        select(Step)
        .where(Step.uid == user.id, Step.aid == aid)
        .order_by(Step.timestamp, Step.id)  # type: ignore[union-attr]
    )
    segments_result = await session.exec(
        select(Segment)
        .where(Segment.uid == user.id, Segment.aid == aid)
        .order_by(Segment.start_time)  # type: ignore[union-attr]
    )
    steps = list(steps_result.all())
    segments = list(segments_result.all())
    return PrintBundle(
        album=album,
        steps=steps,
        segments=segments,
        total_distance_km=_total_distance_km(segments),
    )


@router.post(
    "/{aid}/pdf/generate",
    response_class=EventSourceResponse,
    responses={200: {"model": list[PdfEvent]}},
    dependencies=[Depends(_get_album)],
)
async def generate_pdf(
    aid: str,
    browser: BrowserDep,
    request: Request,
    dark: Annotated[bool, Query()] = True,  # noqa: FBT002
) -> AsyncIterable[PdfEvent]:
    session_cookie = request.cookies.get("session", "")
    async for event in render_album_pdf_stream(
        browser, aid, session_cookie=session_cookie, dark=dark
    ):
        yield event
