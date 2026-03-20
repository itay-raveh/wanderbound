import logging
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Path,
    Query,
    status,
)
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse
from sqlmodel import select

from app.logic.pdf import PdfEvent, pop_pdf_path, render_album_pdf_stream
from app.models.album import Album, AlbumData, AlbumUpdate
from app.models.segment import BoundaryAdjust, Segment, SegmentKind, split_segments
from app.models.step import Step, StepUpdate

from ..deps import BrowserDep, SessionDep, UserDep

logger = logging.getLogger(__name__)


async def _get_album(
    aid: Annotated[str, Path()], user: UserDep, session: SessionDep
) -> Album:
    return await session.get_one(Album, (user.id, aid))


AlbumDep = Annotated[Album, Depends(_get_album)]

router = APIRouter(prefix="/albums", tags=["albums"])


@router.get("/{aid}")
async def read_album(aid: str, album: AlbumDep) -> Album:
    return album


async def _album_data(album: Album, session: SessionDep) -> AlbumData:
    await session.refresh(album, attribute_names=["steps", "segments"])
    return AlbumData(steps=album.steps, segments=album.segments)


@router.get("/{aid}/data")
async def read_album_data(aid: str, album: AlbumDep, session: SessionDep) -> AlbumData:
    return await _album_data(album, session)


@router.patch("/{aid}")
async def update_album(
    aid: str,
    update: AlbumUpdate,
    album: AlbumDep,
    session: SessionDep,
) -> Album:
    album.sqlmodel_update(update.model_dump(exclude_unset=True))
    session.add(album)
    await session.commit()
    await session.refresh(album)
    return album


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
    album: AlbumDep,
    session: SessionDep,
) -> AlbumData:
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

    return await _album_data(album, session)


@router.post(
    "/{aid}/pdf/generate",
    response_class=EventSourceResponse,
    responses={200: {"model": list[PdfEvent]}},
)
async def generate_pdf(
    aid: str,
    user: UserDep,
    browser: BrowserDep,
    dark: Annotated[bool, Query()] = True,  # noqa: FBT002
) -> AsyncIterable[PdfEvent]:
    async for event in render_album_pdf_stream(browser, user, aid, dark=dark):
        yield event


@router.get("/{aid}/pdf/download/{token}")
async def download_pdf(
    aid: str,
    token: str,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    path = pop_pdf_path(token)
    if path is None or not path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Invalid or expired token"
        )
    background_tasks.add_task(path.unlink, missing_ok=True)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{aid}.pdf",
    )
