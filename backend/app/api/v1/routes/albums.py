from collections import Counter
from itertools import chain
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel
from sqlmodel import select

from app.api.v1.deps import USER_COOKIE
from app.core.config import settings
from app.core.logging import config_logger
from app.logic.spatial.segments import Segment, build_segments
from app.models.db import Album, AlbumId, AlbumSettings, Step, StepIdx, StepLayout
from app.models.trips import Locations

from ..deps import AlbumDep, BrowserDep, SessionDep, UserDep

logger = config_logger(__name__)

router = APIRouter(prefix="/albums", tags=["albums"])


@router.get("/{aid}")
async def read_album(aid: AlbumId, album: AlbumDep) -> Album:
    return album


@router.patch("/{aid}")
async def update_album(
    aid: AlbumId,
    update: AlbumSettings,
    album: AlbumDep,
    session: SessionDep,
) -> Album:
    album.sqlmodel_update(update)
    session.add(album)
    await session.commit()
    await session.refresh(album)
    return album


class Range(BaseModel):
    start: int
    end: int


class StepsAndSegments(BaseModel):
    steps: list[Step]
    segments: list[Segment]


@router.post("/{aid}/steps")
async def read_steps(
    aid: AlbumId,
    ranges: list[Range],
    user: UserDep,
    session: SessionDep,
) -> StepsAndSegments:
    indexes = list(chain(*(range(rng.start, rng.end + 1) for rng in ranges)))

    # noinspection PyUnresolvedReferences
    steps = list(
        (
            await session.scalars(
                select(Step)
                .where(Step.uid == user.id, Step.aid == aid, Step.idx.in_(indexes))  # type: ignore[unresolved-attribute]
                .order_by(Step.idx)  # type: ignore[invalid-argument-type]
            )
        ).all()
    )

    if not steps:
        return StepsAndSegments(steps=[], segments=[])

    locations = Locations.from_trip_dir(user.trips_folder / aid).locations
    segments = list(build_segments(steps, locations))  # type: ignore[invalid-argument-type]

    logger.info(
        "Segments: %s",
        Counter(s.kind.name for s in segments),
    )

    return StepsAndSegments(steps=steps, segments=segments)


@router.patch("/{aid}/steps/{sid}")
async def update_step(
    aid: AlbumId,
    sid: StepIdx,
    update: StepLayout,
    user: UserDep,
    session: SessionDep,
) -> Step:
    # noinspection PyTypeChecker
    step: Step = await session.get_one(Step, (user.id, aid, sid))
    step.sqlmodel_update(update)
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
) -> RawResponse:
    context = await browser.new_context()
    await context.add_cookies(
        [
            {"name": USER_COOKIE, "value": str(user.id), "url": settings.FRONTEND_URL},
        ]
    )
    page = await context.new_page()
    url = f"{settings.FRONTEND_URL}/print/{aid}?dark={'true' if dark else 'false'}"
    logger.info("PDF: navigating to %s", url)
    await page.goto(url, wait_until="networkidle")
    pdf_bytes = await page.pdf(
        format="A4",
        landscape=True,
        print_background=True,
    )
    await context.close()
    return RawResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{aid}.pdf"'},
    )
