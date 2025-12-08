"""Photo processing and layout computation for steps."""

from pathlib import Path

from src.core.logger import get_logger
from src.data.layout import StepLayout
from src.data.models import Photo, Step

from .io import load_step_photos
from .layout_engine import select_cover_photo, should_use_cover_photo
from .scorer import compute_default_photos_by_pages

logger = get_logger(__name__)


def process_step_photos(
    step: Step,
    trip_dir: Path,
    layout_override: StepLayout | None = None,
) -> tuple[list[Photo], Photo | None, list[list[Photo]], list[Photo]]:
    """Process photos for a single step, including loading, selection, and layout.

    Args:
        step: The step data.
        trip_dir: Path to the trip directory.
        layout_override: Optional manual layout configuration.

    Returns:
        tuple: (all_photos, cover_photo, pages, hidden_photos)
    """
    photo_dir = _get_step_photo_dir(trip_dir, step)
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
        return [], None, [], []

    photos = load_step_photos(photo_dir)
    if not photos:
        logger.warning(
            "No photos found in %s for step '%s'. Expected image files (.jpg, .jpeg, .png)",
            photo_dir,
            step.city,
        )
        return [], None, [], []

    # --- Manual Layout Override ---
    if layout_override:
        return _apply_manual_layout(photos, layout_override)

    # --- Default Layout Logic ---
    use_cover = should_use_cover_photo(step.description)

    # Determine cover photo (always select one if candidates exist, for map usage)
    cover_photo = select_cover_photo(photos)

    # Only exclude the cover photo from the photo pages if we are actually using it
    # as a cover on the step page.
    excluded_cover = cover_photo if use_cover else None

    # Use default layout strategy
    pages, _, _ = compute_default_photos_by_pages(photos, excluded_cover)

    # If we are NOT using the cover on the step page (use_cover=False),
    # we still return it as 'cover_photo' so the map can use it,
    # but 'pages' will include it so it's not lost.
    # Default behavior: No explicit hidden photos unless overridden.
    return photos, cover_photo, pages, []


def _apply_manual_layout(
    all_photos: list[Photo], layout: StepLayout
) -> tuple[list[Photo], Photo | None, list[list[Photo]], list[Photo]]:
    """Apply manual layout configuration to the loaded photos."""
    photo_map = {p.id: p for p in all_photos}

    cover_photo = _resolve_cover_photo(layout, photo_map)
    hidden_photos, used_photo_ids = _resolve_hidden_photos(layout, photo_map)

    if cover_photo:
        used_photo_ids.add(cover_photo.id)

    pages = _build_pages(layout, photo_map, cover_photo, used_photo_ids)
    _rescue_orphans(all_photos, used_photo_ids, pages, layout.step_id)

    return all_photos, cover_photo, pages, hidden_photos


def _resolve_cover_photo(layout: StepLayout, photo_map: dict[str, Photo]) -> Photo | None:
    if layout.cover_photo_id and layout.cover_photo_id in photo_map:
        return photo_map[layout.cover_photo_id]
    return None


def _resolve_hidden_photos(
    layout: StepLayout, photo_map: dict[str, Photo]
) -> tuple[list[Photo], set[str]]:
    used_photo_ids: set[str] = set()
    hidden_photos: list[Photo] = []

    if layout.hidden_photos:
        logger.debug("Step %s has %d hidden photos", layout.step_id, len(layout.hidden_photos))
        used_photo_ids.update(layout.hidden_photos)
        # Populate hidden_photos list using list comprehension/extend logic
        hidden_photos.extend([photo_map[pid] for pid in layout.hidden_photos if pid in photo_map])
    return hidden_photos, used_photo_ids


def _build_pages(
    layout: StepLayout,
    photo_map: dict[str, Photo],
    cover_photo: Photo | None,
    used_photo_ids: set[str],
) -> list[list[Photo]]:
    pages: list[list[Photo]] = []
    for page_layout in layout.pages:
        current_page: list[Photo] = []
        for photo_id in page_layout.photos:
            # Skip if this is the cover photo
            if cover_photo and photo_id == cover_photo.id:
                continue

            if photo_id in photo_map:
                current_page.append(photo_map[photo_id])
                used_photo_ids.add(photo_id)
            else:
                logger.warning("Layout references missing photo: %s", photo_id)
        if current_page:
            pages.append(current_page)
    return pages


def _rescue_orphans(
    all_photos: list[Photo],
    used_photo_ids: set[str],
    pages: list[list[Photo]],
    step_id: int,
) -> None:
    orphans = [p for p in all_photos if p.id not in used_photo_ids]

    if orphans:
        logger.info("Step %s has %d orphan photos; adding to grid.", step_id, len(orphans))
        if not pages:
            pages.append([])
        # Prepend orphans to the first page
        pages[0] = orphans + pages[0]


def _get_step_photo_dir(trip_dir: Path, step: Step) -> Path | None:
    slug = step.slug or step.display_slug or ""

    if not slug:
        return None

    # Try both patterns: slug_id and display_slug_id
    patterns = [
        f"{slug}_{step.id}",
        f"{step.display_slug or slug}_{step.id}",
    ]

    for pattern in patterns:
        photo_dir = trip_dir / pattern / "photos"
        if photo_dir.exists():
            return photo_dir

    return None
