"""Photo processing and layout computation for steps."""

from pathlib import Path

from .image_selector import (
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
) -> tuple[list[Photo], Photo | None, list[list[Photo]]]:
    """Process photos for a single step, including loading, selection, and layout.

    Returns empty lists/None if no photos are found.

    Args:
        step: Step object to process photos for.
        trip_dir: Base trip directory containing step folders.

    Returns:
        Tuple of:
            - List of Photo objects for the step
            - Cover photo (Photo or None)
            - List of photo pages (each page is a list of Photo objects)
    """
    from .utils.paths import get_step_photo_dir

    photo_dir = get_step_photo_dir(trip_dir, step)
    if not photo_dir:
        logger.warning(
            f"No photo directory found for step '{step.city}' (ID: {step.id}). "
            f"Expected directory pattern: {step.slug or step.display_slug}_{step.id}/photos "
            f"in {trip_dir}"
        )
        return [], None, []

    photos = load_step_photos(photo_dir)
    if not photos:
        logger.warning(
            f"No photos found in {photo_dir} for step '{step.city}'. "
            f"Expected image files (.jpg, .jpeg, .png)"
        )
        return [], None, []

    use_cover = should_use_cover_photo(step.description)

    # Determine cover photo
    cover_photo = select_cover_photo(photos) if use_cover else None

    # Use default layout strategy
    pages, _, _ = compute_default_photos_by_pages(photos, cover_photo)
    return photos, cover_photo, pages
