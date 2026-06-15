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


async def validate_album_chapters(  # noqa: C901
    session: AsyncSession,
    album: Album,
    update: AlbumUpdate,
) -> None:
    if "chapters" not in update.model_fields_set:
        return

    chapters = update.chapters or []
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

    if not requested:
        return

    result = await session.exec(
        select(Step.id).where(
            Step.uid == album.uid,
            Step.aid == album.id,
            col(Step.id).in_(requested),
        )
    )
    existing = set(result.all())
    missing = sorted(requested - existing)
    if missing:
        joined = ", ".join(str(step_id) for step_id in missing)
        raise ChapterValidationError(f"Unknown chapter step IDs: {joined}")


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
    projected = AlbumWithMedia.model_validate({**album.model_dump(), "media": media})
    projected.title = chapter.title if chapter.title is not None else album.title
    projected.subtitle = (
        chapter.subtitle if chapter.subtitle is not None else album.subtitle
    )
    projected.front_cover_photo = chapter.front_cover_photo
    projected.back_cover_photo = chapter.back_cover_photo
    projected.maps_ranges = map_ranges_for_steps(album.maps_ranges, steps)
    return projected
