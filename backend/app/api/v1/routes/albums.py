import logging
from collections.abc import AsyncIterable, Sequence
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
from sqlmodel import col, select

from app.logic.layout.media import Media
from app.logic.pdf import PdfEvent, pop_pdf_token, render_album_pdf_stream
from app.logic.route_matching import MATCHABLE_KINDS, total_length_km
from app.models.album import Album, AlbumMeta, AlbumUpdate, PrintBundle
from app.models.segment import (
    BoundaryAdjust,
    Segment,
    SegmentKind,
    SegmentOutline,
    split_segments,
)
from app.models.step import Step, StepUpdate
from app.services.mapbox import match_segments

from ..deps import BrowserDep, HttpClientsDep, SessionDep, UserDep, apply_update

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
        .order_by(col(Step.timestamp), col(Step.id))
    )
    return list(result.all())


@router.get("/{aid}/segments")
async def read_segments(
    aid: str, user: UserDep, session: SessionDep
) -> list[SegmentOutline]:
    result = await session.exec(
        select(Segment)
        .where(Segment.uid == user.id, Segment.aid == aid)
        .order_by(col(Segment.start_time))
    )
    return [SegmentOutline.from_segment(s) for s in result.all()]


@router.get("/{aid}/segments/points")
async def read_segment_points(  # noqa: PLR0913
    aid: str,
    user: UserDep,
    session: SessionDep,
    http: HttpClientsDep,
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
        .order_by(col(Segment.start_time))
    )
    segments = result.all()

    # Auto-match driving/walking segments that don't have a route yet
    unmatched = [s for s in segments if s.kind in MATCHABLE_KINDS and s.route is None]
    if unmatched:
        pairs = [([(p.lon, p.lat) for p in s.points], str(s.kind)) for s in unmatched]
        routes = await match_segments(http.mapbox, pairs)
        for seg, route in zip(unmatched, routes, strict=True):
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
    await apply_update(session, album, update)
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
    return await apply_update(session, step, update)


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
        ordering = col(Segment.end_time).desc()
    else:
        time_filter = Segment.start_time >= target.end_time
        ordering = col(Segment.start_time).asc()
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
        .order_by(col(Segment.start_time))
    )
    return [SegmentOutline.from_segment(s) for s in result.all()]


def _total_distance_km(segments: list[Segment]) -> float:
    return round(
        sum(total_length_km([(p.lon, p.lat) for p in seg.points]) for seg in segments),
        1,
    )


@router.get("/{aid}/print-bundle")
async def read_print_bundle(
    aid: str, album: AlbumDep, user: UserDep, session: SessionDep
) -> PrintBundle:
    steps_result = await session.exec(
        select(Step)
        .where(Step.uid == user.id, Step.aid == aid)
        .order_by(col(Step.timestamp), col(Step.id))
    )
    segments_result = await session.exec(
        select(Segment)
        .where(Segment.uid == user.id, Segment.aid == aid)
        .order_by(col(Segment.start_time))
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
