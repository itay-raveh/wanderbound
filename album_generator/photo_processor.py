"""Photo processing and layout computation for steps."""

from pathlib import Path
from typing import Any

from .image_selector import (
    _is_one_portrait_two_landscapes,
    _is_three_portraits,
    compute_default_photos_by_pages,
    load_step_photos,
    select_cover_photo,
    should_use_cover_photo,
)
from .logger import get_logger
from .models import Photo, Step

logger = get_logger(__name__)

__all__ = ["process_step_photos"]


def process_step_photos(
    step: Step,
    trip_dir: Path,
    photo_config: dict[int, dict[str, Any]] | None,
) -> tuple[list[Photo], Photo | None, list[list[Photo]], list[bool], list[bool]]:
    """Process photos for a single step, including loading, selection, and layout.

    Handles both saved configuration and automatic photo selection/layout.
    Returns empty lists/None if no photos are found.

    Args:
        step: Step object to process photos for.
        trip_dir: Base trip directory containing step folders.
        photo_config: Optional saved photo configuration dictionary.

    Returns:
        Tuple of:
            - List of Photo objects for the step
            - Cover photo (Photo or None)
            - List of photo pages (each page is a list of Photo objects)
            - List of is_three_portraits flags (one per page)
            - List of is_portrait_landscape_split flags (one per page)
    """
    from .data_loader import get_step_photo_dir

    photo_dir = get_step_photo_dir(trip_dir, step)
    if not photo_dir:
        logger.warning(
            f"No photo directory found for step '{step.city}' (ID: {step.id}). "
            f"Expected directory pattern: {step.slug or step.display_slug}_{step.id}/photos "
            f"in {trip_dir}"
        )
        return [], None, [], [], []

    photos = load_step_photos(photo_dir)
    if not photos:
        logger.warning(
            f"No photos found in {photo_dir} for step '{step.city}'. "
            f"Expected image files (.jpg, .jpeg, .png)"
        )
        return [], None, [], [], []

    use_cover = should_use_cover_photo(step.description)

    # Check if we have saved configuration for this step
    if photo_config and step.id in photo_config:
        config = photo_config[step.id]
        cover_photo_index = config.get("cover_photo_index")
        if cover_photo_index:
            cover_photo = next((p for p in photos if p.index == cover_photo_index), None)
            cover_photo = cover_photo if use_cover else None
        else:
            cover_photo = select_cover_photo(photos) if use_cover else None

        photo_pages_indices = config.get("photo_pages", [])
        if photo_pages_indices:
            photo_pages: list[list[Photo]] = []
            photos_by_index = {p.index: p for p in photos}
            for page_indices in photo_pages_indices:
                page_photos = [
                    photos_by_index[idx] for idx in page_indices if idx in photos_by_index
                ]
                if page_photos:
                    photo_pages.append(page_photos)

            saved_is_three_portraits = config.get("is_three_portraits", [])
            saved_is_portrait_landscape_split = config.get("is_portrait_landscape_split", [])

            if len(saved_is_three_portraits) == len(photo_pages):
                is_three_portraits = saved_is_three_portraits
            else:
                computed_is_three_portraits: list[bool] = []
                for page in photo_pages:
                    computed_is_three_portraits.append(
                        len(page) == 3 and _is_three_portraits(tuple(page))
                    )
                is_three_portraits = computed_is_three_portraits

            if len(saved_is_portrait_landscape_split) == len(photo_pages):
                is_portrait_landscape_split = saved_is_portrait_landscape_split
            else:
                computed_is_portrait_landscape_split: list[bool] = []
                for page in photo_pages:
                    computed_is_portrait_landscape_split.append(
                        len(page) == 3 and _is_one_portrait_two_landscapes(tuple(page))
                    )
                is_portrait_landscape_split = computed_is_portrait_landscape_split

            return photos, cover_photo, photo_pages, is_three_portraits, is_portrait_landscape_split
        else:
            # Use default layout strategy
            pages, layouts, split_layouts = compute_default_photos_by_pages(photos, cover_photo)
            return photos, cover_photo, pages, layouts, split_layouts
    else:
        # No saved config: use automatic selection
        cover_photo = select_cover_photo(photos) if use_cover else None
        pages, layouts, split_layouts = compute_default_photos_by_pages(photos, cover_photo)
        return photos, cover_photo, pages, layouts, split_layouts
