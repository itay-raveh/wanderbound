from typing import TYPE_CHECKING

from sqlmodel import col, select

from app.models.album import (
    Album,
    AlbumChapter,
    AlbumUpdate,
    AlbumWithMedia,
    DateRange,
)
from app.models.album_media import AlbumMedia
from app.models.segment import Segment
from app.models.step import Step, StepRead

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


class ChapterValidationError(ValueError):
    pass


DEFAULT_CHAPTER_ID = "chapter-1"


def default_album_chapter(
    *,
    title: str,
    subtitle: str,
    step_ids: list[int],
    front_cover_photo: str,
    back_cover_photo: str,
) -> AlbumChapter:
    return AlbumChapter(
        id=DEFAULT_CHAPTER_ID,
        title=title,
        subtitle=subtitle,
        step_ids=step_ids,
        front_cover_photo=front_cover_photo,
        back_cover_photo=back_cover_photo,
    )


async def validate_album_chapters(  # noqa: C901
    session: AsyncSession,
    album: Album,
    update: AlbumUpdate,
) -> None:
    if "chapters" not in update.model_fields_set:
        return

    chapters = update.chapters or []
    if not chapters:
        raise ChapterValidationError("Album must have at least one chapter")

    assigned: set[int] = set()
    duplicates: list[int] = []
    requested: set[int] = set()
    chapter_ids: set[str] = set()

    for chapter in chapters:
        if chapter.id in chapter_ids:
            raise ChapterValidationError(f"Duplicate chapter ID: {chapter.id}")
        chapter_ids.add(chapter.id)
        if not chapter.step_ids:
            raise ChapterValidationError(f"Chapter {chapter.id} has no steps")

        for step_id in chapter.step_ids:
            if step_id in assigned:
                duplicates.append(step_id)
            assigned.add(step_id)
            requested.add(step_id)

    if duplicates:
        step_id = duplicates[0]
        raise ChapterValidationError(
            f"Step {step_id} is already assigned to another chapter"
        )

    result = await session.exec(
        select(Step.id).where(
            Step.uid == album.uid,
            Step.aid == album.id,
        )
    )
    existing = set(result.all())
    missing = sorted(requested - existing)
    if missing:
        joined = ", ".join(str(step_id) for step_id in missing)
        raise ChapterValidationError(f"Unknown chapter step IDs: {joined}")

    unassigned = sorted(existing - requested)
    if unassigned:
        joined = ", ".join(str(step_id) for step_id in unassigned)
        raise ChapterValidationError(f"Missing chapter step IDs: {joined}")


async def ensure_album_chapters(session: AsyncSession, album: Album) -> Album:
    if album.chapters and any(chapter.step_ids for chapter in album.chapters):
        return album

    result = await session.exec(
        select(Step.id)
        .where(
            Step.uid == album.uid,
            Step.aid == album.id,
        )
        .order_by(col(Step.timestamp))
    )
    step_ids = list(result.all())
    if not step_ids:
        return album

    existing = album.chapters[0] if album.chapters else None
    album.chapters = [
        default_album_chapter(
            title=existing.title if existing else "",
            subtitle=existing.subtitle if existing else "",
            step_ids=step_ids,
            front_cover_photo=existing.front_cover_photo if existing else "",
            back_cover_photo=existing.back_cover_photo if existing else "",
        )
    ]
    session.add(album)
    await session.commit()
    await session.refresh(album)
    return album


def find_chapter(album: Album, chapter_id: str) -> AlbumChapter | None:
    return next(
        (chapter for chapter in album.chapters if chapter.id == chapter_id),
        None,
    )


def steps_for_chapter(steps: list[StepRead], chapter: AlbumChapter) -> list[StepRead]:
    wanted = set(chapter.step_ids)
    return [step for step in steps if step.id in wanted]


def segments_for_steps(segments: list[Segment], steps: list[StepRead]) -> list[Segment]:
    if not steps:
        return []
    start = steps[0].timestamp
    end = steps[-1].timestamp
    return [
        segment
        for segment in segments
        if segment.start_time <= end and segment.end_time >= start
    ]


def map_ranges_for_steps(
    ranges: list[DateRange],
    steps: list[StepRead],
) -> list[DateRange]:
    step_dates = {step.datetime.date() for step in steps}
    return [
        date_range
        for date_range in ranges
        if any(date_range[0] <= step_date <= date_range[1] for step_date in step_dates)
    ]


def album_for_chapter(
    album: Album,
    media: list[AlbumMedia],
    chapter: AlbumChapter,
    steps: list[StepRead],
) -> AlbumWithMedia:
    projected = AlbumWithMedia.model_validate(
        {**album.model_dump(), "chapters": [chapter], "media": media}
    )
    projected.maps_ranges = map_ranges_for_steps(album.maps_ranges, steps)
    return projected
