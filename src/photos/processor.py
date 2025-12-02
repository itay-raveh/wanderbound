"""Photo processing and layout computation for steps."""

from pathlib import Path

from src.core.logger import get_logger
from src.data.models import Photo, Step
from src.utils.paths import get_step_photo_dir

from .io import load_step_photos
from .layout_engine import select_cover_photo, should_use_cover_photo
from .scorer import compute_default_photos_by_pages

logger = get_logger(__name__)


def process_step_photos(
    step: Step,
    trip_dir: Path,
) -> tuple[list[Photo], Photo | None, list[list[Photo]]]:
    """Process photos for a single step, including loading, selection, and layout.

    Returns empty lists/None if no photos are found.
    """
    photo_dir = get_step_photo_dir(trip_dir, step)
    if not photo_dir:
        logger.warning(
            "No photo directory found for step '%s' (ID: %s). "
            "Expected directory pattern: %s_%s/photos in %s",
            step.city,
            step.id,
            step.slug or step.display_slug,
            step.id,
            trip_dir,
        )
        return [], None, []

    photos = load_step_photos(photo_dir)
    if not photos:
        logger.warning(
            "No photos found in %s for step '%s'. Expected image files (.jpg, .jpeg, .png)",
            photo_dir,
            step.city,
        )
        return [], None, []

    use_cover = should_use_cover_photo(step.description)

    # Determine cover photo
    cover_photo = select_cover_photo(photos) if use_cover else None

    # Use default layout strategy
    pages, _, _ = compute_default_photos_by_pages(photos, cover_photo)
    return photos, cover_photo, pages
