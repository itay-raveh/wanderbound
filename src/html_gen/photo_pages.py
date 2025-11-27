"""Photo page processing and layout detection for HTML generation."""

from pathlib import Path

from src.logger import get_logger
from src.models import Photo
from src.photo.layout import _is_one_portrait_two_landscapes, _is_three_portraits
from src.type_definitions import PhotoPageData

from .asset_management import copy_image_to_assets

logger = get_logger(__name__)

__all__ = ["process_photo_pages"]


def process_photo_pages(
    photo_pages: list[list[Photo]],
    step_name: str,
    output_dir: Path,
) -> list[PhotoPageData]:
    """Process photo pages and copy images to assets directory.

    Calculates layout flags on-the-fly based on photo aspect ratios.

    Args:
        photo_pages: List of photo pages, each page is a list of Photo objects
        step_name: Step name for file naming
        output_dir: Output directory (parent of assets/)

    Returns:
        List of PhotoPageData objects with image paths and layout flags
    """
    photo_pages_paths: list[PhotoPageData] = []

    for page in photo_pages:
        page_paths: list[str] = [
            copy_image_to_assets(photo.path, output_dir, step_name, photo.index)
            for photo in page
            if photo.path.exists()
        ]

        if page_paths:
            # Calculate layout flags on-the-fly based on photo aspect ratios
            is_three_portraits = False
            is_portrait_landscape_split = False

            if len(page) == 3:
                if _is_three_portraits(tuple(page)):
                    is_three_portraits = True
                    is_portrait_landscape_split = False
                elif _is_one_portrait_two_landscapes(tuple(page)):
                    is_three_portraits = False
                    is_portrait_landscape_split = True

            photo_pages_paths.append(
                PhotoPageData(
                    photos=page_paths,
                    is_three_portraits=is_three_portraits,
                    is_portrait_landscape_split=is_portrait_landscape_split,
                )
            )

    return photo_pages_paths
