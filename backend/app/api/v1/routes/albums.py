import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response

from app.core.config import settings
from app.models.album import Album, AlbumData, AlbumUpdate
from app.models.ids import AlbumId, StepIdx
from app.models.step import Step, StepUpdate

from ..deps import USER_COOKIE, BrowserDep, SessionDep, UserDep

logger = logging.getLogger(__name__)


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


@router.post("/{aid}/pdf")
async def export_pdf(
    aid: AlbumId,
    user: UserDep,
    browser: BrowserDep,
    dark: Annotated[bool, Query()] = True,  # noqa: FBT002
) -> Response:
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        device_scale_factor=2,
    )
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
        page.on("console", lambda msg: logger.debug("Browser: %s", msg.text))
        page.on(
            "pageerror",
            lambda err: logger.warning("Browser page error during PDF render: %s", err),
        )
        # Activate @media print CSS before navigation so layout matches PDF output.
        await page.emulate_media(media="print")
        url = f"{settings.FRONTEND_URL}/print/{aid}?dark={'true' if dark else 'false'}"
        await page.goto(url, wait_until="domcontentloaded")
        logger.info("DOM loaded for album %s", aid)
        await page.wait_for_function("window.__PRINT_READY__ === true", timeout=60_000)
        pdf_bytes = await page.pdf(
            prefer_css_page_size=True,
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        logger.info("PDF generated for album %s: %d bytes", aid, len(pdf_bytes))
    finally:
        await context.close()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{aid}.pdf"'},
    )
