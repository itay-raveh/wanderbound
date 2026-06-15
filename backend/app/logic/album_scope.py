from app.logic.chapters import (
    album_for_chapter,
    find_chapter,
    segments_for_steps,
    steps_for_chapter,
)
from app.logic.spatial.geo import total_length_km
from app.models.album import Album, AlbumWithMedia, PrintBundle
from app.models.album_media import AlbumMedia
from app.models.segment import Segment
from app.models.step import StepRead


class ChapterNotFoundError(ValueError):
    pass


def total_distance_km(segments: list[Segment]) -> float:
    return round(
        sum(total_length_km([(p.lon, p.lat) for p in seg.points]) for seg in segments),
        1,
    )


def build_print_bundle_scope(
    album: Album,
    media: list[AlbumMedia],
    steps: list[StepRead],
    segments: list[Segment],
    *,
    chapter_id: str | None,
) -> PrintBundle:
    if chapter_id is None:
        return PrintBundle(
            album=AlbumWithMedia(**album.model_dump(), media=media),
            steps=steps,
            segments=segments,
            total_distance_km=total_distance_km(segments),
        )

    chapter = find_chapter(album, chapter_id)
    if chapter is None:
        raise ChapterNotFoundError("Chapter not found")

    scoped_steps = steps_for_chapter(steps, chapter)
    scoped_segments = segments_for_steps(segments, scoped_steps)
    return PrintBundle(
        album=album_for_chapter(album, media, chapter, scoped_steps),
        steps=scoped_steps,
        segments=scoped_segments,
        total_distance_km=total_distance_km(scoped_segments),
    )
