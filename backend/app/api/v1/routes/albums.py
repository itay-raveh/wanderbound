from collections.abc import AsyncIterable, Sequence
from typing import Annotated

import structlog
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

from app.logic.album_scope import ChapterNotFoundError, build_print_bundle_scope
from app.logic.chapters import (
    ChapterValidationError,
    update_album_settings,
)
from app.logic.pdf import (
    PdfEvent,
    pop_pdf_token,
    render_album_pdf_stream,
)
from app.logic.pdf_chapters import render_album_chapters_zip_stream
from app.logic.segment_routes import enqueue_album_route_enrichment
from app.logic.step_media import (
    read_step_with_media,
    read_steps_with_media,
    replace_step_media_layout,
)
from app.models.album import Album, AlbumMeta, AlbumUpdate, PrintBundle
from app.models.album_media import AlbumMedia
from app.models.segment import (
    BoundaryAdjust,
    Segment,
    SegmentKind,
    SegmentOutline,
    split_segments,
)
from app.models.step import Step, StepMediaLayout, StepRead, StepUpdate

from ..deps import BrowserDep, HttpClientsDep, SessionDep, UserDep, apply_update

logger = structlog.get_logger(__name__)


async def _get_album(
    aid: Annotated[str, Path()], user: UserDep, session: SessionDep
) -> Album:
    return await session.get_one(Album, (user.id, aid))


AlbumDep = Annotated[Album, Depends(_get_album)]

router = APIRouter(prefix="/albums", tags=["albums"])


def _validate_pdf_chapter(
    album: AlbumDep,
    chapter: Annotated[str | None, Query()] = None,
) -> str | None:
    if chapter is not None and not _ordered_existing_chapter_ids(album, [chapter]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Chapter not found")
    return chapter


def _ordered_existing_chapter_ids(
    album: Album,
    chapter_ids: list[str] | None,
) -> list[str]:
    if not chapter_ids:
        return [chapter.id for chapter in album.chapters]
    selected = set(chapter_ids)
    return [chapter.id for chapter in album.chapters if chapter.id in selected]


def _validate_pdf_chapters(
    album: AlbumDep,
    chapters: Annotated[list[str] | None, Query()] = None,
) -> list[str]:
    ordered = _ordered_existing_chapter_ids(album, chapters)
    if chapters and len(ordered) != len(set(chapters)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Chapter not found")
    return ordered


# Static-prefix routes must be declared before /{aid} to avoid shadowing.
@router.get("/pdf/download/{token}")
async def download_pdf(
    token: str,
    background_tasks: BackgroundTasks,
    session: SessionDep,
) -> FileResponse:
    result = await pop_pdf_token(session, token)
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Invalid or expired token"
        )
    background_tasks.add_task(result.path.unlink, missing_ok=True)
    return FileResponse(
        result.path,
        media_type=result.media_type,
        filename=result.filename,
    )


@router.get("/{aid}")
async def read_album(aid: str, album: AlbumDep) -> AlbumMeta:
    return AlbumMeta.model_validate(album)


@router.get("/{aid}/media")
async def read_media(
    aid: str, album: AlbumDep, session: SessionDep
) -> list[AlbumMedia]:
    result = await session.exec(
        select(AlbumMedia)
        .where(AlbumMedia.uid == album.uid, AlbumMedia.aid == aid)
        .order_by(col(AlbumMedia.created_at), col(AlbumMedia.name))
    )
    return list(result.all())


@router.get("/{aid}/steps")
async def read_steps(aid: str, user: UserDep, session: SessionDep) -> list[StepRead]:
    return await read_steps_with_media(session, user.id, aid)


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
        .order_by(col(Segment.start_time))
    )
    return result.all()


@router.patch("/{aid}")
async def update_album(
    aid: str,
    update: AlbumUpdate,
    album: AlbumDep,
    session: SessionDep,
) -> AlbumMeta:
    try:
        await update_album_settings(session, album, update)
    except ChapterValidationError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return AlbumMeta.model_validate(album)


@router.patch("/{aid}/steps/{sid}")
async def update_step(
    aid: str,
    sid: int,
    update: StepUpdate,
    user: UserDep,
    session: SessionDep,
) -> StepRead:
    step: Step = await session.get_one(Step, (user.id, aid, sid))
    await apply_update(session, step, update)
    return await read_step_with_media(session, user.id, aid, sid)


@router.put("/{aid}/steps/{sid}/media-layout")
async def update_step_media_layout(
    aid: str,
    sid: int,
    layout: StepMediaLayout,
    user: UserDep,
    session: SessionDep,
) -> StepRead:
    try:
        return await replace_step_media_layout(session, user.id, aid, sid, layout)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.patch("/{aid}/segments/adjust-boundary")
async def adjust_segment_boundary(  # noqa: PLR0913
    aid: str,
    body: BoundaryAdjust,
    user: UserDep,
    session: SessionDep,
    http: HttpClientsDep,
    background_tasks: BackgroundTasks,
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
    enqueue_album_route_enrichment(background_tasks, http, uid, aid)

    logger.info(
        "segment.boundary_adjusted",
        user_id=uid,
        album_id=aid,
        handle=body.handle,
    )

    result = await session.exec(
        select(Segment)
        .where(Segment.uid == uid, Segment.aid == aid)
        .order_by(col(Segment.start_time))
    )
    return [SegmentOutline.from_segment(s) for s in result.all()]


@router.get("/{aid}/print-bundle")
async def read_print_bundle(
    aid: str,
    album: AlbumDep,
    user: UserDep,
    session: SessionDep,
    chapter: Annotated[str | None, Query()] = None,
) -> PrintBundle:
    media_result = await session.exec(
        select(AlbumMedia)
        .where(AlbumMedia.uid == user.id, AlbumMedia.aid == aid)
        .order_by(col(AlbumMedia.created_at), col(AlbumMedia.name))
    )
    segments_result = await session.exec(
        select(Segment)
        .where(Segment.uid == user.id, Segment.aid == aid)
        .order_by(col(Segment.start_time))
    )
    media_rows = list(media_result.all())
    steps = await read_steps_with_media(session, user.id, aid)
    segments = list(segments_result.all())
    try:
        return build_print_bundle_scope(
            album,
            media_rows,
            steps,
            segments,
            chapter_id=chapter,
        )
    except ChapterNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post(
    "/{aid}/pdf/generate",
    response_class=EventSourceResponse,
    responses={200: {"model": list[PdfEvent]}},
    dependencies=[Depends(_get_album)],
)
async def generate_pdf(  # noqa: PLR0913
    aid: str,
    browser: BrowserDep,
    request: Request,
    session: SessionDep,
    dark: Annotated[bool, Query()] = True,  # noqa: FBT002
    chapter: Annotated[str | None, Depends(_validate_pdf_chapter)] = None,
) -> AsyncIterable[PdfEvent]:
    session_cookie = request.cookies.get("session", "")
    async for event in render_album_pdf_stream(
        browser,
        session,
        aid,
        session_cookie=session_cookie,
        dark=dark,
        chapter=chapter,
    ):
        yield event


@router.post(
    "/{aid}/pdf/generate-chapters",
    response_class=EventSourceResponse,
    responses={200: {"model": list[PdfEvent]}},
    dependencies=[Depends(_get_album)],
)
async def generate_chapters_pdf(  # noqa: PLR0913
    aid: str,
    browser: BrowserDep,
    request: Request,
    session: SessionDep,
    chapter_ids: Annotated[list[str], Depends(_validate_pdf_chapters)],
    dark: Annotated[bool, Query()] = True,  # noqa: FBT002
) -> AsyncIterable[PdfEvent]:
    session_cookie = request.cookies.get("session", "")
    async for event in render_album_chapters_zip_stream(
        browser,
        session,
        aid,
        chapter_ids,
        session_cookie=session_cookie,
        dark=dark,
    ):
        yield event
