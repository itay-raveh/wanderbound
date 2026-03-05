import asyncio
from itertools import combinations
from typing import TYPE_CHECKING

from app.core.logging import config_logger
from app.logic.layout.strategies import (
    FourLandscapesStrategy,
    LayoutStrategy,
    OneLandscapeStrategy,
    OnePortraitTwoLandscapesStrategy,
    ThreeLandscapesStrategy,
    ThreePortraitsStrategy,
    TwoPortraitsStrategy,
)

from .media import Media, Photo, Video

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable
    from pathlib import Path

    from app.models.db import AlbumId, User
    from app.models.trips import PSStep

logger = config_logger(__name__)

# In order of preference
_STRATEGIES: list[LayoutStrategy] = [
    ThreePortraitsStrategy(),
    OnePortraitTwoLandscapesStrategy(),
    FourLandscapesStrategy(),
    TwoPortraitsStrategy(),
    ThreeLandscapesStrategy(),
    OneLandscapeStrategy(),
]


def _try_build_page(candidates: Collection[Media]) -> list[Media] | None:
    for strategy in _STRATEGIES:
        if strategy.required_count > len(candidates):
            continue

        for combo in combinations(candidates, strategy.required_count):
            if strategy.validate(combo):
                return strategy.sort(combo)
    return None


def _build_page_layouts(photos: Iterable[Media]) -> list[list[Path]]:
    candidates = set(photos)

    # Divide photos intp pages
    pages: list[list[Path]] = []
    while candidates:
        if layout := _try_build_page(candidates):
            pages.append([media.path for media in layout])
            candidates -= set(layout)
        else:
            # If no strategies work, give some photo its own page,
            # and we will try again with the rest
            pages.append([candidates.pop().path])

    return pages


async def build_step_layout(
    user: User,
    aid: AlbumId,
    step: PSStep,
) -> tuple[Path, list[list[Path]]]:
    assets_in_folder: list[Media] = []

    # Load Photos
    photo_folder = user.trips_folder / aid / step.folder_name / "photos"
    if photo_folder.exists():
        assets_in_folder.extend(
            await asyncio.gather(
                *(Photo.load(user.folder, path) for path in photo_folder.iterdir())
            )
        )

    # Load Videos
    video_folder = user.trips_folder / aid / step.folder_name / "videos"
    if video_folder.exists():
        assets_in_folder.extend(
            await asyncio.gather(
                *(Video.load(user.folder, path) for path in video_folder.iterdir())
            )
        )

    # Portraits, sorted from 4/5 (perfect size) downwards
    portraits = sorted(
        (photo for photo in assets_in_folder if photo.is_portrait),
        key=lambda photo: photo.aspect_ratio,
        reverse=True,
    )

    # Select cover
    cover = portraits[0] if portraits else assets_in_folder[0]

    # If it appears on the step page, remove it from the photo pages
    if not step.is_long_description:
        assets_in_folder.remove(cover)

    # Run combinatorial layout search in a separate thread
    pages = await asyncio.to_thread(_build_page_layouts, assets_in_folder)

    return cover.path, pages
