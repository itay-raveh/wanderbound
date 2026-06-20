from datetime import UTC, date, datetime

import pytest

from app.logic.album_scope import (
    ChapterNotFoundError,
    build_print_bundle_scope,
    total_distance_km,
)
from app.models.album import AlbumChapter
from tests.factories import make_album, make_album_media, make_segment, make_step_read


def _timestamp(year: int, month: int, day: int) -> float:
    return datetime(year, month, day, tzinfo=UTC).timestamp()


def test_build_print_bundle_scope_projects_chapter_fields_and_filters_content() -> None:
    album = make_album(
        title="Whole Trip",
        subtitle="Full route",
        front_cover_photo="album-front.jpg",
        back_cover_photo="album-back.jpg",
    )
    album.maps_ranges = [
        (date(2024, 1, 1), date(2024, 1, 31)),
        (date(2024, 3, 1), date(2024, 3, 31)),
    ]
    album.chapters = [
        AlbumChapter(
            id="chapter-1",
            title="First Chapter",
            subtitle="",
            step_ids=[1, 2],
            front_cover_photo="chapter-front.jpg",
            back_cover_photo="chapter-back.jpg",
        )
    ]
    media = [make_album_media()]
    steps = [
        make_step_read(step_id=1, timestamp=_timestamp(2024, 1, 10)),
        make_step_read(step_id=2, timestamp=_timestamp(2024, 1, 20)),
        make_step_read(step_id=3, timestamp=_timestamp(2024, 3, 10)),
    ]
    segments = [
        make_segment(
            start_time=_timestamp(2024, 1, 9),
            end_time=_timestamp(2024, 1, 21),
        ),
        make_segment(
            start_time=_timestamp(2024, 3, 9),
            end_time=_timestamp(2024, 3, 11),
        ),
    ]

    bundle = build_print_bundle_scope(
        album,
        media,
        steps,
        segments,
        chapter_id="chapter-1",
    )

    assert bundle.album.chapters[0].title == "First Chapter"
    assert bundle.album.chapters[0].subtitle == ""
    assert bundle.album.chapters[0].front_cover_photo == "chapter-front.jpg"
    assert bundle.album.chapters[0].back_cover_photo == "chapter-back.jpg"
    assert [step.id for step in bundle.steps] == [1, 2]
    assert [segment.start_time for segment in bundle.segments] == [
        _timestamp(2024, 1, 9)
    ]
    assert bundle.album.maps_ranges == [(date(2024, 1, 1), date(2024, 1, 31))]
    assert bundle.total_distance_km == total_distance_km(bundle.segments)


def test_build_print_bundle_scope_rejects_unknown_chapter() -> None:
    album = make_album()

    with pytest.raises(ChapterNotFoundError, match="Chapter not found"):
        build_print_bundle_scope(
            album,
            [],
            [],
            [],
            chapter_id="missing",
        )
