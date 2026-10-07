from collections import defaultdict
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete
from sqlmodel import col, select

from app.models.album_media import (
    AlbumMedia,
    StepPage,
    StepPageSlot,
    StepUnusedMedia,
)
from app.models.step import (
    Step,
    StepMediaLayout,
    StepPageLayout,
    StepRead,
    StepSlotLayout,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


def _step_to_read(
    step: Step,
    page_rows: list[StepPage],
    slot_rows: list[StepPageSlot],
    unused_rows: list[StepUnusedMedia],
) -> StepRead:
    slots_by_page: dict[str, list[StepSlotLayout]] = defaultdict(list)
    for row in slot_rows:
        slots_by_page[row.page_id].append(
            StepSlotLayout(
                id=UUID(row.id),
                kind=row.kind,
                media_name=row.media_name,
                text=row.text_content,
                frame_orientation=row.frame_orientation,
                continuation_priority=row.continuation_priority,
            )
        )

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
        pages=[
            StepPageLayout(
                id=UUID(row.id),
                kind=row.page_kind,
                slots=slots_by_page[row.id],
            )
            for row in page_rows
        ],
        unused=[row.media_name for row in unused_rows],
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
                select(StepPage)
                .where(StepPage.uid == uid, StepPage.aid == aid)
                .order_by(
                    col(StepPage.step_id),
                    col(StepPage.position_index),
                )
            )
        ).all()
    )
    slot_rows = list(
        (
            await session.exec(
                select(StepPageSlot)
                .where(StepPageSlot.uid == uid, StepPageSlot.aid == aid)
                .order_by(
                    col(StepPageSlot.step_id),
                    col(StepPageSlot.page_id),
                    col(StepPageSlot.position_index),
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

    pages_by_step: dict[int, list[StepPage]] = defaultdict(list)
    for row in page_rows:
        pages_by_step[row.step_id].append(row)
    slots_by_step: dict[int, list[StepPageSlot]] = defaultdict(list)
    for row in slot_rows:
        slots_by_step[row.step_id].append(row)
    unused_by_step: dict[int, list[StepUnusedMedia]] = defaultdict(list)
    for row in unused_rows:
        unused_by_step[row.step_id].append(row)

    return [
        _step_to_read(
            step,
            pages_by_step[step.id],
            slots_by_step[step.id],
            unused_by_step[step.id],
        )
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
                select(StepPage)
                .where(
                    StepPage.uid == uid,
                    StepPage.aid == aid,
                    StepPage.step_id == step_id,
                )
                .order_by(col(StepPage.position_index))
            )
        ).all()
    )
    slot_rows = list(
        (
            await session.exec(
                select(StepPageSlot)
                .where(
                    StepPageSlot.uid == uid,
                    StepPageSlot.aid == aid,
                    StepPageSlot.step_id == step_id,
                )
                .order_by(col(StepPageSlot.page_id), col(StepPageSlot.position_index))
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
    return _step_to_read(step, page_rows, slot_rows, unused_rows)


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
    names = {name for page in layout.pages for name in page.media}
    names.update(layout.unused)
    if layout.cover is not None:
        names.add(layout.cover)
    return names


def step_media_rows(
    uid: int,
    aid: str,
    step_id: int,
    pages: list[StepPageLayout],
    unused: list[str],
) -> list[StepPage | StepPageSlot | StepUnusedMedia]:
    page_rows = [
        StepPage(
            uid=uid,
            aid=aid,
            step_id=step_id,
            id=str(page.id),
            position_index=position_index,
            page_kind=page.kind,
        )
        for position_index, page in enumerate(pages)
    ]
    slot_rows = [
        StepPageSlot(
            uid=uid,
            aid=aid,
            step_id=step_id,
            id=str(slot.id),
            page_id=str(page.id),
            position_index=position_index,
            kind=slot.kind,
            media_name=slot.media_name,
            text_content=slot.text,
            frame_orientation=slot.frame_orientation,
            continuation_priority=slot.continuation_priority
            if slot.continuation_priority is not None
            else sum(len(previous.slots) for previous in pages[:page_index])
            + position_index,
        )
        for page_index, page in enumerate(pages)
        for position_index, slot in enumerate(page.slots)
    ]
    unused_rows = [
        StepUnusedMedia(
            uid=uid,
            aid=aid,
            step_id=step_id,
            position_index=position_index,
            media_name=media_name,
        )
        for position_index, media_name in enumerate(unused)
    ]
    return [*page_rows, *slot_rows, *unused_rows]


async def replace_step_media_layout(  # noqa: C901
    session: AsyncSession,
    uid: int,
    aid: str,
    step_id: int,
    layout: StepMediaLayout,
) -> StepRead:
    step = await session.get_one(Step, (uid, aid, step_id))
    await _validate_media_names(session, uid, aid, _layout_names(layout))
    existing_pages = {
        row.id: row
        for row in (
            await session.exec(
                select(StepPage).where(
                    StepPage.uid == uid,
                    StepPage.aid == aid,
                    StepPage.step_id == step_id,
                )
            )
        ).all()
    }
    existing_slots = {
        row.id: row
        for row in (
            await session.exec(
                select(StepPageSlot).where(
                    StepPageSlot.uid == uid,
                    StepPageSlot.aid == aid,
                    StepPageSlot.step_id == step_id,
                )
            )
        ).all()
    }
    next_priority = (
        max((row.continuation_priority for row in existing_slots.values()), default=-1)
        + 1
    )
    incoming_page_ids = {str(page.id) for page in layout.pages}
    incoming_slot_ids = {str(slot.id) for page in layout.pages for slot in page.slots}
    for slot_id, row in existing_slots.items():
        if slot_id not in incoming_slot_ids:
            await session.delete(row)
    await session.flush()

    for position_index, page in enumerate(layout.pages):
        page_id = str(page.id)
        row = existing_pages.get(page_id)
        if row is None:
            row = StepPage(
                uid=uid,
                aid=aid,
                step_id=step_id,
                id=page_id,
                position_index=position_index,
            )
        row.position_index = position_index
        row.page_kind = page.kind
        session.add(row)
    await session.flush()

    for page in layout.pages:
        for position_index, slot in enumerate(page.slots):
            slot_id = str(slot.id)
            row = existing_slots.get(slot_id)
            if row is None:
                row = StepPageSlot(
                    uid=uid,
                    aid=aid,
                    step_id=step_id,
                    id=slot_id,
                    page_id=str(page.id),
                    position_index=position_index,
                    kind=slot.kind,
                    continuation_priority=next_priority,
                )
                next_priority += 1
            row.page_id = str(page.id)
            row.position_index = position_index
            row.kind = slot.kind
            row.media_name = slot.media_name
            row.text_content = slot.text
            row.frame_orientation = slot.frame_orientation
            session.add(row)
    await session.flush()
    for page_id, row in existing_pages.items():
        if page_id not in incoming_page_ids:
            await session.delete(row)
    await session.exec(
        delete(StepUnusedMedia).where(
            col(StepUnusedMedia.uid) == uid,
            col(StepUnusedMedia.aid) == aid,
            col(StepUnusedMedia.step_id) == step_id,
        )
    )
    step.cover_media_name = layout.cover
    session.add(step)
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
