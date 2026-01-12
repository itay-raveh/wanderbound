"""Photo processing and layout computation for steps."""

from pathlib import Path

from src.core.logger import get_logger
from src.data.layout import StepLayout
from src.data.models import PhotoWithDims, Step

from .io import load_single_photo, load_step_photos
from .layout_engine import select_cover_photo, should_use_cover_photo
from .scorer import compute_default_photos_by_pages

logger = get_logger(__name__)


def process_step_photos(
    step: Step,
    trip_dir: Path,
    global_used_ids: set[Path],
    layout_override: StepLayout | None = None,
) -> tuple[list[PhotoWithDims], Path | None, list[list[PhotoWithDims]], list[Path]]:
    """Process photos for a single step, including loading, selection, and layout.

    Args:
        step: The step data.
        trip_dir: Path to the trip directory.
        global_used_ids: Set of photo IDs used in other steps (to prevent orphans).
        layout_override: Optional manual layout configuration.

    Returns:
        tuple: (all_photos, cover_photo, pages, hidden_photos)
    """
    photo_dir = _get_step_photo_dir(trip_dir, step)
    if not photo_dir:
        logger.warning(
            "No photo directory found for step '%s' (ID: %s). "
            "Expected directory pattern: %s_%s/photos in %s",
            step.name,
            step.id,
            step.slug,
            step.id,
            trip_dir,
        )
        return [], None, [], []

    photos = load_step_photos(photo_dir)
    if not photos:
        logger.warning(
            "No photos found in %s for step '%s'",
            photo_dir,
            step.name,
        )
        return [], None, [], []

    # --- Manual Layout Override ---
    if layout_override:
        return *_apply_manual_layout(
            step, photos, layout_override, global_used_ids
        ), layout_override.hidden_photos  # ty:ignore[invalid-return-type]

    # --- Default Layout Logic ---

    # Determine cover photo (always select one if candidates exist, for map usage)
    cover_photo = select_cover_photo(photos)

    excluded_cover = cover_photo if should_use_cover_photo(step.description) else None

    pages = compute_default_photos_by_pages(photos, excluded_cover)

    return photos, cover_photo.path if cover_photo else None, pages, []


def _apply_manual_layout(
    step: Step,
    local_photos: list[PhotoWithDims],
    layout: StepLayout,
    global_used_photos: set[Path],
) -> tuple[list[PhotoWithDims], Path | None, list[list[PhotoWithDims]]]:
    photo_map = {p.path: p for p in local_photos}

    all_needed_paths = set()
    if layout.cover_photo:
        all_needed_paths.add(layout.cover_photo)
    all_needed_paths.update(layout.hidden_photos)
    for page in layout.pages:
        all_needed_paths.update(page.photos)

    for path in all_needed_paths:
        if path not in photo_map:
            photo_map[path] = load_single_photo(path)

    used_photos: set[Path] = set()
    if layout.hidden_photos:
        used_photos.update(layout.hidden_photos)
    if layout.cover_photo and should_use_cover_photo(step.description):
        used_photos.add(layout.cover_photo)

    pages = _build_pages(layout, photo_map, used_photos)

    orphans = {p1.path for p1 in local_photos} - used_photos - global_used_photos

    if orphans:
        logger.warning("Step %s has %d orphan photos: %s", layout.step_id, len(orphans), orphans)
        if not pages:
            pages.append([])
        pages[0] += list(orphans)

    return list(photo_map.values()), layout.cover_photo, pages


def _build_pages(
    layout: StepLayout,
    photo_map: dict[Path, PhotoWithDims],
    used_photos: set[Path],
) -> list[list[PhotoWithDims]]:
    pages: list[list[PhotoWithDims]] = []
    for old_page in layout.pages:
        updated_page: list[PhotoWithDims] = []
        for path in old_page.photos:
            if path in photo_map and path not in used_photos:
                updated_page.append(photo_map[path])
                used_photos.add(path)
            else:
                logger.warning("Layout references missing photo: %s", path)
        if updated_page:
            pages.append(updated_page)
    return pages


def _get_step_photo_dir(trip_dir: Path, step: Step) -> Path | None:
    photo_dir = trip_dir / step.dir_name / "photos"
    if photo_dir.exists():
        return photo_dir

    return None
