from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from sqlmodel import col, select

from app.logic.step_media import read_step_with_media, replace_step_media_layout
from app.models.album_media import StepPage, StepPageMedia
from app.models.step import StepMediaLayout, StepPageLayout
from tests.factories import AID, insert_album, insert_album_media, insert_step

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


async def test_read_step_with_media_returns_grid_layout_for_existing_page_rows(
    session: AsyncSession,
) -> None:
    await insert_album(session, 1)
    await insert_album_media(session, 1, name="first.jpg")
    await insert_album_media(session, 1, name="second.jpg")
    await insert_step(session, 1, page_media_name=None, unused_media_name=None)
    session.add(StepPage(uid=1, aid=AID, step_id=1, page_index=0, kind="grid"))
    session.add_all(
        [
            StepPageMedia(
                uid=1,
                aid=AID,
                step_id=1,
                page_index=0,
                position_index=0,
                media_name="first.jpg",
            ),
            StepPageMedia(
                uid=1,
                aid=AID,
                step_id=1,
                page_index=0,
                position_index=1,
                media_name="second.jpg",
            ),
        ]
    )
    await session.flush()

    result = await read_step_with_media(session, 1, AID, 1)

    assert result.pages == [
        StepPageLayout(kind="grid", media=["first.jpg", "second.jpg"])
    ]


@pytest.mark.parametrize("media", [[], ["first.jpg", "second.jpg"]])
def test_panorama_spread_requires_exactly_one_media_name(media: list[str]) -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        StepPageLayout(kind="panorama_spread", media=media)


async def test_replace_step_media_layout_preserves_page_and_media_order(
    session: AsyncSession,
) -> None:
    await insert_album(session, 1)
    for name in ("first.jpg", "second.jpg", "third.jpg", "fourth.jpg"):
        await insert_album_media(session, 1, name=name)
    await insert_step(session, 1, page_media_name=None, unused_media_name=None)

    result = await replace_step_media_layout(
        session,
        1,
        AID,
        1,
        StepMediaLayout(
            cover=None,
            pages=[
                StepPageLayout(kind="grid", media=["second.jpg", "first.jpg"]),
                StepPageLayout(kind="panorama_spread", media=["third.jpg"]),
            ],
            unused=["fourth.jpg"],
        ),
    )

    page_rows = list(
        (await session.exec(select(StepPage).order_by(col(StepPage.page_index)))).all()
    )
    assert result.pages == [
        StepPageLayout(kind="grid", media=["second.jpg", "first.jpg"]),
        StepPageLayout(kind="panorama_spread", media=["third.jpg"]),
    ]
    assert [(page.page_index, page.kind) for page in page_rows] == [
        (0, "grid"),
        (1, "panorama_spread"),
    ]
