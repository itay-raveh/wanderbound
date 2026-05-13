from collections import defaultdict
from typing import TYPE_CHECKING

from sqlalchemy import delete
from sqlmodel import col, select

from app.models.album_media import AlbumMedia, StepPageMedia, StepUnusedMedia
from app.models.step import Step, StepMediaLayout, StepRead

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


def _step_to_read(
    step: Step,
    page_rows: list[StepPageMedia],
    unused_rows: list[StepUnusedMedia],
) -> StepRead:
    pages_by_index: dict[int, list[str]] = defaultdict(list)
    for row in sorted(page_rows, key=lambda r: (r.page_index, r.position_index)):
        pages_by_index[row.page_index].append(row.media_name)

    return StepRead(
        uid=step.uid,
        aid=step.aid,
        id=step.id,
        name=step.name,
        description=step.description,
        timestamp=step.timestamp,
        timezone_id=step.timezone_id,
        location=step.location,
        elevation=step.elevation,
        weather=step.weather,
        cover=step.cover_media_name,
        pages=[pages_by_index[i] for i in sorted(pages_by_index)],
        unused=[
            row.media_name
            for row in sorted(unused_rows, key=lambda r: r.position_index)
        ],
    )


async def read_steps_with_media(
    session: AsyncSession, uid: int, aid: str
) -> list[StepRead]:
    steps = list(
        (
            await session.exec(
                select(Step)
                .where(Step.uid == uid, Step.aid == aid)
                .order_by(col(Step.timestamp), col(Step.id))
            )
        ).all()
    )
    if not steps:
        return []

    page_rows = list(
        (
            await session.exec(
                select(StepPageMedia)
                .where(StepPageMedia.uid == uid, StepPageMedia.aid == aid)
                .order_by(
                    col(StepPageMedia.step_id),
                    col(StepPageMedia.page_index),
                    col(StepPageMedia.position_index),
                )
            )
        ).all()
    )
    unused_rows = list(
        (
            await session.exec(
                select(StepUnusedMedia)
                .where(StepUnusedMedia.uid == uid, StepUnusedMedia.aid == aid)
                .order_by(
                    col(StepUnusedMedia.step_id),
                    col(StepUnusedMedia.position_index),
                )
            )
        ).all()
    )

    pages_by_step: dict[int, list[StepPageMedia]] = defaultdict(list)
    for row in page_rows:
        pages_by_step[row.step_id].append(row)
    unused_by_step: dict[int, list[StepUnusedMedia]] = defaultdict(list)
    for row in unused_rows:
        unused_by_step[row.step_id].append(row)

    return [
        _step_to_read(step, pages_by_step[step.id], unused_by_step[step.id])
        for step in steps
    ]


async def read_step_with_media(
    session: AsyncSession,
    uid: int,
    aid: str,
    step_id: int,
) -> StepRead:
    step = await session.get_one(Step, (uid, aid, step_id))
    page_rows = list(
        (
            await session.exec(
                select(StepPageMedia)
                .where(
                    StepPageMedia.uid == uid,
                    StepPageMedia.aid == aid,
                    StepPageMedia.step_id == step_id,
                )
                .order_by(
                    col(StepPageMedia.page_index),
                    col(StepPageMedia.position_index),
                )
            )
        ).all()
    )
    unused_rows = list(
        (
            await session.exec(
                select(StepUnusedMedia)
                .where(
                    StepUnusedMedia.uid == uid,
                    StepUnusedMedia.aid == aid,
                    StepUnusedMedia.step_id == step_id,
                )
                .order_by(col(StepUnusedMedia.position_index))
            )
        ).all()
    )
    return _step_to_read(step, page_rows, unused_rows)


async def _validate_media_names(
    session: AsyncSession,
    uid: int,
    aid: str,
    names: set[str],
) -> None:
    if not names:
        return
    existing = set(
        (
            await session.exec(
                select(AlbumMedia.name).where(
                    AlbumMedia.uid == uid,
                    AlbumMedia.aid == aid,
                    col(AlbumMedia.name).in_(names),
                )
            )
        ).all()
    )
    missing = sorted(names - existing)
    if missing:
        raise ValueError(f"Media not found: {', '.join(missing)}")


def _layout_names(layout: StepMediaLayout) -> set[str]:
    names = {name for page in layout.pages for name in page}
    names.update(layout.unused)
    if layout.cover is not None:
        names.add(layout.cover)
    return names


async def replace_step_media_layout(
    session: AsyncSession,
    uid: int,
    aid: str,
    step_id: int,
    layout: StepMediaLayout,
) -> StepRead:
    step = await session.get_one(Step, (uid, aid, step_id))
    await _validate_media_names(session, uid, aid, _layout_names(layout))

    await session.exec(
        delete(StepPageMedia).where(
            col(StepPageMedia.uid) == uid,
            col(StepPageMedia.aid) == aid,
            col(StepPageMedia.step_id) == step_id,
        )
    )
    await session.exec(
        delete(StepUnusedMedia).where(
            col(StepUnusedMedia.uid) == uid,
            col(StepUnusedMedia.aid) == aid,
            col(StepUnusedMedia.step_id) == step_id,
        )
    )

    step.cover_media_name = layout.cover
    session.add(step)
    for page_index, page in enumerate(layout.pages):
        for position_index, media_name in enumerate(page):
            session.add(
                StepPageMedia(
                    uid=uid,
                    aid=aid,
                    step_id=step_id,
                    page_index=page_index,
                    position_index=position_index,
                    media_name=media_name,
                )
            )
    for position_index, media_name in enumerate(layout.unused):
        session.add(
            StepUnusedMedia(
                uid=uid,
                aid=aid,
                step_id=step_id,
                position_index=position_index,
                media_name=media_name,
            )
        )

    await session.commit()
    await session.refresh(step)
    return await read_step_with_media(session, uid, aid, step_id)


async def prepend_step_unused_media(
    session: AsyncSession,
    uid: int,
    aid: str,
    step_id: int,
    names: list[str],
) -> None:
    existing = list(
        (
            await session.exec(
                select(StepUnusedMedia)
                .where(
                    StepUnusedMedia.uid == uid,
                    StepUnusedMedia.aid == aid,
                    StepUnusedMedia.step_id == step_id,
                )
                .order_by(col(StepUnusedMedia.position_index))
            )
        ).all()
    )
    await session.exec(
        delete(StepUnusedMedia).where(
            col(StepUnusedMedia.uid) == uid,
            col(StepUnusedMedia.aid) == aid,
            col(StepUnusedMedia.step_id) == step_id,
        )
    )
    merged = [*names, *(row.media_name for row in existing)]
    for position_index, media_name in enumerate(merged):
        session.add(
            StepUnusedMedia(
                uid=uid,
                aid=aid,
                step_id=step_id,
                position_index=position_index,
                media_name=media_name,
            )
        )
