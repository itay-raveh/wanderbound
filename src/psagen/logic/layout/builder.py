"""Photo scoring and bin-packing algorithms for page layout."""

import asyncio
from collections.abc import Collection, Iterable
from itertools import combinations
from pathlib import Path

from psagen.core.logger import get_logger
from psagen.logic.layout.strategies import (
    FourLandscapesStrategy,
    LayoutStrategy,
    OneLandscapeStrategy,
    OnePortraitTwoLandscapesStrategy,
    ThreeLandscapesStrategy,
    ThreePortraitsStrategy,
    TwoPortraitsStrategy,
)
from psagen.logic.media import load_photo, load_video
from psagen.models.layout import PageLayout, Photo, StepLayout, Video
from psagen.models.trip import Step

logger = get_logger(__name__)

# In order of preference
_STRATEGIES: list[LayoutStrategy] = [
    ThreePortraitsStrategy(),
    OnePortraitTwoLandscapesStrategy(),
    FourLandscapesStrategy(),
    TwoPortraitsStrategy(),
    ThreeLandscapesStrategy(),
    OneLandscapeStrategy(),
]


def try_build_layout(photos: Collection[Photo]) -> PageLayout | None:
    for strategy in _STRATEGIES:
        if strategy.required_count == len(photos) and strategy.validate(photos):
            return PageLayout(photos=strategy.sort(photos), layout_class=strategy.layout_class)
    return None


def _try_build_page(candidates: Collection[Photo]) -> PageLayout | None:
    for strategy in _STRATEGIES:
        if strategy.required_count > len(candidates):
            continue

        for combo in combinations(candidates, strategy.required_count):
            if strategy.validate(combo):
                return PageLayout(
                    photos=strategy.sort(combo),
                    layout_class=strategy.layout_class,
                )
    return None


def _build_page_layouts(photos: Iterable[Photo]) -> list[PageLayout]:
    candidates = set(photos)

    # Divide photos intp pages
    pages: list[PageLayout] = []
    while candidates:
        if layout := _try_build_page(candidates):
            pages.append(layout)
            candidates -= set(layout.photos)
        else:
            # If no strategies work, give some photo its own page,
            # and we will try again with the rest
            pages.append(PageLayout(photos=[candidates.pop()], layout_class=None))

    return pages


def _select_cover(photos: list[Photo]) -> Photo:
    portraits = [photo for photo in photos if photo.is_portrait]

    if portraits:
        return portraits[0]

    return photos[0]


async def build_step_layout(
    trip_dir: Path,
    step: Step,
) -> StepLayout:
    assets_in_folder: list[Video | Photo] = []

    # Load Photos
    photo_folder = trip_dir / step.folder_name / "photos"
    if photo_folder.exists():
        assets_in_folder.extend(
            await asyncio.gather(*(load_photo(trip_dir, path) for path in photo_folder.iterdir()))
        )

    # Try select cover
    cover: Photo | None = None
    if assets_in_folder:
        cover = _select_cover(assets_in_folder)

    # Load Videos
    video_folder = trip_dir / step.folder_name / "videos"
    if video_folder.exists():
        videos = await asyncio.gather(
            *(load_video(trip_dir, path) for path in video_folder.iterdir())
        )
        assets_in_folder.extend(videos)

    cover = cover or _select_cover(assets_in_folder)

    # If it appears on the step page, remove it from the photo pages
    if not step.is_long_description:
        assets_in_folder.remove(cover)

    # Run combinatorial layout search in a separate thread
    pages = await asyncio.to_thread(_build_page_layouts, assets_in_folder)

    return StepLayout(
        id=step.id,
        name=step.name,
        cover=cover.path,
        pages=pages,
        hidden_photos=[],
    )
