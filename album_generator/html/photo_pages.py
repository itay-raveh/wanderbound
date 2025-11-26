"""Photo page processing and layout detection for HTML generation."""

from pathlib import Path

from ..logger import get_logger
from ..models import Photo
from ..photo.layout import _is_one_portrait_two_landscapes, _is_three_portraits
from ..photo.ratio import get_photo_ratio
from ..types import PhotoPageData
from .asset_management import copy_image_to_assets

logger = get_logger(__name__)

__all__ = ["process_photo_pages"]


def process_photo_pages(
    photo_pages: list[list[Photo]],
    photo_page_layouts: list[bool],
    photo_page_portrait_split_layouts: list[bool],
    step_name: str,
    output_dir: Path,
) -> list[PhotoPageData]:
    """Process photo pages and copy images to assets directory.

    Args:
        photo_pages: List of photo pages, each page is a list of Photo objects
        photo_page_layouts: List of is_three_portraits flags (one per page)
        photo_page_portrait_split_layouts: List of is_portrait_landscape_split flags (one per page)
        step_name: Step name for file naming
        output_dir: Output directory (parent of assets/)

    Returns:
        List of PhotoPageData objects with image paths and layout flags
    """
    photo_pages_paths: list[PhotoPageData] = []

    for page_idx, page in enumerate(photo_pages):
        page_paths: list[str] = []
        for photo in page:
            if photo.path.exists():
                page_paths.append(
                    copy_image_to_assets(photo.path, output_dir, step_name, photo.index)
                )

        if page_paths:
            # Get the layout flags for this page
            is_three_portraits = False
            is_portrait_landscape_split = False
            if page_idx < len(photo_page_layouts):
                is_three_portraits = photo_page_layouts[page_idx]
            if page_idx < len(photo_page_portrait_split_layouts):
                is_portrait_landscape_split = photo_page_portrait_split_layouts[page_idx]

            # Safety check: if we have exactly 3 photos, double-check the layout
            # This ensures the flag is set even if there was a mismatch in the layout array
            if len(page) == 3:
                if _is_three_portraits(tuple(page)):
                    is_three_portraits = True
                    is_portrait_landscape_split = False
                    logger.debug(
                        f"Detected 3 portraits in html_generator, forcing layout for page {page_idx}"
                    )
                elif _is_one_portrait_two_landscapes(tuple(page)):
                    is_three_portraits = False
                    is_portrait_landscape_split = True
                    logger.debug(
                        f"Detected 1 portrait + 2 landscapes in html_generator, forcing split layout for page {page_idx}"
                    )
                else:
                    # Check what we actually have
                    ratios = [get_photo_ratio(p.width or 0, p.height or 0) for p in page]
                    logger.debug(
                        f"Page with 3 photos but no special layout in html_generator. Page {page_idx}, "
                        f"ratios: {[r.name for r in ratios]}, dimensions: {[(p.width, p.height) for p in page]}"
                    )

            photo_pages_paths.append(
                PhotoPageData(
                    photos=page_paths,
                    is_three_portraits=is_three_portraits,
                    is_portrait_landscape_split=is_portrait_landscape_split,
                )
            )

    return photo_pages_paths
