import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response

from app.api.v1.deps import USER_COOKIE
from app.core.browser import get_browser
from app.core.config import settings
from app.models.album import Album, AlbumData, AlbumUpdate
from app.models.step import Step, StepUpdate
from app.models.types import AlbumId, StepIdx

from ..deps import SessionDep, UserDep

logger = logging.getLogger(__name__)


async def _get_album(
    aid: Annotated[AlbumId, Path()], user: UserDep, session: SessionDep
) -> Album:
    # noinspection PyTypeChecker
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
    # noinspection PyTypeChecker
    step: Step = await session.get_one(Step, (user.id, aid, sid))
    step.sqlmodel_update(update.model_dump(exclude_unset=True))
    session.add(step)
    await session.commit()
    await session.refresh(step)
    return step


@router.post("/{aid}/pdf")
async def export_pdf(
    aid: AlbumId,
    user: UserDep,
    dark: Annotated[bool, Query()] = True,  # noqa: FBT002
) -> Response:
    context = await get_browser().new_context()
    try:
        await context.add_cookies(
            [
                {
                    "name": USER_COOKIE,
                    "value": str(user.id),
                    "url": settings.FRONTEND_URL,
                },
            ]
        )
        page = await context.new_page()
        url = f"{settings.FRONTEND_URL}/print/{aid}?dark={'true' if dark else 'false'}"
        await page.goto(url, wait_until="networkidle")
        pdf_bytes = await page.pdf(
            format="A4",
            landscape=True,
            print_background=True,
        )
        logger.info("PDF generated for album %s: %d bytes", aid, len(pdf_bytes))
    finally:
        await context.close()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{aid}.pdf"'},
    )
