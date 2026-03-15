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

from app.logic.pdf import PdfEvent, pop_pdf_path, render_album_pdf_stream
from app.models.album import Album, AlbumData, AlbumUpdate
from app.models.ids import AlbumId, StepIdx
from app.models.step import Step, StepUpdate

from ..deps import BrowserDep, SessionDep, UserDep


async def _get_album(
    aid: Annotated[AlbumId, Path()], user: UserDep, session: SessionDep
) -> Album:
    return await session.get_one(Album, (user.id, aid))


AlbumDep = Annotated[Album, Depends(_get_album)]

router = APIRouter(prefix="/albums", tags=["albums"])


@router.get("/{aid}")
async def read_album(aid: AlbumId, album: AlbumDep) -> Album:
    return album


@router.get("/{aid}/data")
async def read_album_data(
    aid: AlbumId, album: AlbumDep, session: SessionDep
) -> AlbumData:
    await session.refresh(album, attribute_names=["steps", "segments"])
    return AlbumData(steps=album.steps, segments=album.segments)


@router.patch("/{aid}")
async def update_album(
    aid: AlbumId,
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
    aid: AlbumId,
    sid: StepIdx,
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


@router.post(
    "/{aid}/pdf/generate",
    response_class=EventSourceResponse,
    responses={200: {"model": list[PdfEvent]}},
)
async def generate_pdf(
    aid: AlbumId,
    user: UserDep,
    browser: BrowserDep,
    dark: Annotated[bool, Query()] = True,  # noqa: FBT002
) -> AsyncIterable[PdfEvent]:
    async for event in render_album_pdf_stream(browser, user, aid, dark=dark):
        yield event


@router.get("/{aid}/pdf/download/{token}")
async def download_pdf(
    aid: AlbumId,
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
