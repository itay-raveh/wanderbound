"""Photo processing and layout computation for steps."""

from collections.abc import Callable
from pathlib import Path

from .image_selector import (
    compute_default_photos_by_pages,
    load_step_photos,
    select_cover_photo,
    should_use_cover_photo,
)
from .logger import get_logger
from .models import Photo, Step
from .photo.layout import _is_one_portrait_two_landscapes, _is_three_portraits
from .types import PhotoConfigDict

logger = get_logger(__name__)

__all__ = ["process_step_photos"]


def process_step_photos(
    step: Step,
    trip_dir: Path,
    photo_config: dict[int, PhotoConfigDict] | None,
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

    # Determine cover photo
    cover_photo = _get_cover_photo(step, photos, photo_config, use_cover)

    # Check if we have saved configuration for this step
    if photo_config and step.id in photo_config:
        config = photo_config[step.id]
        photo_pages_indices = config.get("photo_pages", [])
        if photo_pages_indices:
            photo_pages = _reconstruct_photo_pages(photos, photo_pages_indices)
            is_three_portraits = _compute_layout_flags(
                photo_pages,
                config.get("is_three_portraits", []),
                lambda p: len(p) == 3 and _is_three_portraits(tuple(p)),
            )
            is_portrait_landscape_split = _compute_layout_flags(
                photo_pages,
                config.get("is_portrait_landscape_split", []),
                lambda p: len(p) == 3 and _is_one_portrait_two_landscapes(tuple(p)),
            )
            return photos, cover_photo, photo_pages, is_three_portraits, is_portrait_landscape_split

    # Use default layout strategy (no saved config or no saved pages)
    pages, layouts, split_layouts = compute_default_photos_by_pages(photos, cover_photo)
    return photos, cover_photo, pages, layouts, split_layouts


def _get_cover_photo(
    step: Step,
    photos: list[Photo],
    photo_config: dict[int, PhotoConfigDict] | None,
    use_cover: bool,
) -> Photo | None:
    """Get cover photo from config or auto-select.

    Args:
        step: Step object.
        photos: List of available photos.
        photo_config: Optional saved photo configuration.
        use_cover: Whether to use a cover photo.

    Returns:
        Cover photo or None.
    """
    if not use_cover:
        return None

    if photo_config and step.id in photo_config:
        config = photo_config[step.id]
        cover_photo_index = config.get("cover_photo_index")
        if cover_photo_index:
            return next((p for p in photos if p.index == cover_photo_index), None)

    return select_cover_photo(photos)


def _reconstruct_photo_pages(
    photos: list[Photo], photo_pages_indices: list[list[int]]
) -> list[list[Photo]]:
    """Reconstruct photo pages from saved indices.

    Args:
        photos: List of available Photo objects.
        photo_pages_indices: List of page indices from saved config.

    Returns:
        List of photo pages, each page is a list of Photo objects.
    """
    photo_pages: list[list[Photo]] = []
    photos_by_index = {p.index: p for p in photos}
    for page_indices in photo_pages_indices:
        page_photos = [photos_by_index[idx] for idx in page_indices if idx in photos_by_index]
        if page_photos:
            photo_pages.append(page_photos)
    return photo_pages


def _compute_layout_flags(
    photo_pages: list[list[Photo]],
    saved_flags: list[bool],
    compute_fn: Callable[[list[Photo]], bool],
) -> list[bool]:
    """Compute layout flags, using saved flags if they match page count.

    Args:
        photo_pages: List of photo pages.
        saved_flags: Saved layout flags from config.
        compute_fn: Function to compute flag for a single page.

    Returns:
        List of layout flags, one per page.
    """
    if len(saved_flags) == len(photo_pages):
        return saved_flags

    computed_flags: list[bool] = []
    for page in photo_pages:
        computed_flags.append(compute_fn(page))
    return computed_flags
