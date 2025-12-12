"""Photo processing and layout computation for steps."""

from pathlib import Path

from src.core.logger import get_logger
from src.data.layout import StepLayout
from src.data.models import Photo, Step

from .io import load_single_photo, load_step_photos
from .layout_engine import select_cover_photo, should_use_cover_photo
from .registry import PhotoRegistry
from .scorer import compute_default_photos_by_pages

logger = get_logger(__name__)


def process_step_photos(
    step: Step,
    trip_dir: Path,
    photo_registry: PhotoRegistry,
    global_used_ids: set[str],
    layout_override: StepLayout | None = None,
) -> tuple[list[Photo], Photo | None, list[list[Photo]], list[Photo]]:
    """Process photos for a single step, including loading, selection, and layout.

    Args:
        step: The step data.
        trip_dir: Path to the trip directory.
        photo_registry: Registry of all photos in the trip.
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
            "No photos found in %s for step '%s'. Expected image files (.jpg, .jpeg, .png)",
            photo_dir,
            step.name,
        )
        return [], None, [], []

    # --- Manual Layout Override ---
    if layout_override:
        return _apply_manual_layout(photos, layout_override, photo_registry, global_used_ids)

    # --- Default Layout Logic ---

    # Determine cover photo (always select one if candidates exist, for map usage)
    cover_photo = select_cover_photo(photos)

    # Only exclude the cover photo from the photo pages if we are actually using it
    # as a cover on the step page.
    excluded_cover = cover_photo if should_use_cover_photo(step.description) else None

    # Use default layout strategy
    pages = compute_default_photos_by_pages(photos, excluded_cover)

    # If we are NOT using the cover on the step page (use_cover=False),
    # we still return it as 'cover_photo' so the map can use it,
    # but 'pages' will include it so it's not lost.
    # Default behavior: No explicit hidden photos unless overridden.
    return photos, cover_photo, pages, []


def _apply_manual_layout(
    local_photos: list[Photo],
    layout: StepLayout,
    photo_registry: PhotoRegistry,
    global_used_ids: set[str],
) -> tuple[list[Photo], Photo | None, list[list[Photo]], list[Photo]]:
    """Apply manual layout configuration to the loaded photos.

    In Virtual Move mode:
    1. 'local_photos' are what is physically in the step folder.
    2. 'layout' may reference photos from OTHER folders.
    3. We must resolve those references using 'photo_registry'.
    """
    # 1. Build a map of ALL available photos (Local + Registry for layout IDs)
    photo_map = {p.id: p for p in local_photos}

    # helper to fetch/create photo object from registry if missing locally
    def get_or_load_photo(p_id: str) -> Photo | None:
        path = photo_registry.get_photo_path(p_id)
        if path:
            # Create a transient Photo object
            # Virtual index (validation requirement)
            return load_single_photo(path, 9999)
        return None

    # We actually need to ensure ALL layout IDs are loaded.
    all_needed_ids = set()
    if layout.cover_photo_id:
        all_needed_ids.add(layout.cover_photo_id)
    all_needed_ids.update(layout.hidden_photos)
    for page in layout.pages:
        all_needed_ids.update(page.photos)

    for p_id in all_needed_ids:
        if p_id not in photo_map:
            # Try to resolve from registry
            photo = get_or_load_photo(p_id)
            if photo:
                photo_map[p_id] = photo

    # Re-construct all_photos from the map to include virtual ones
    # (Only matters for passing downstream, but orphans logic uses local_photos)

    cover_photo = _resolve_cover_photo(layout, photo_map)
    hidden_photos, used_photo_ids = _resolve_hidden_photos(layout, photo_map)

    if cover_photo:
        used_photo_ids.add(cover_photo.id)

    pages = _build_pages(layout, photo_map, used_photo_ids)

    # Rescue Orphans:
    # Only rescue photos that are physically here (local_photos)
    # AND are NOT used in this layout
    # AND represent a file that is NOT used in ANY OTHER step (global check)
    _rescue_orphans(local_photos, used_photo_ids, pages, layout.step_id, global_used_ids)

    # Combined list for return
    final_photo_list = list(photo_map.values())

    return final_photo_list, cover_photo, pages, hidden_photos


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
        hidden_photos.extend(
            [photo_map[photo] for photo in layout.hidden_photos if photo in photo_map]
        )
    return hidden_photos, used_photo_ids


def _build_pages(
    layout: StepLayout,
    photo_map: dict[str, Photo],
    used_photo_ids: set[str],
) -> list[list[Photo]]:
    pages: list[list[Photo]] = []
    for page_layout in layout.pages:
        current_page: list[Photo] = []
        for photo_id in page_layout.photos:
            if photo_id in photo_map:
                current_page.append(photo_map[photo_id])
                used_photo_ids.add(photo_id)
            else:
                logger.warning("Layout references missing photo: %s", photo_id)
        if current_page:
            pages.append(current_page)
    return pages


def _rescue_orphans(
    local_photos: list[Photo],
    used_photo_ids: set[str],
    pages: list[list[Photo]],
    step_id: int,
    global_used_ids: set[str],
) -> None:
    # orphan Candidates: Local photos not used in THIS step's layout
    candidates = [p for p in local_photos if p.id not in used_photo_ids]

    # Filter out candidates that are used in OTHER steps
    # (If a photo is moved virtualy to Step B, Step B puts it in global_used_ids.
    #  Step A (here) sees it as orphan candidate.
    #  We must check if it's currently claimed elsewhere.)
    orphans = []
    for p in candidates:
        if p.id in global_used_ids:
            # It's used somewhere else (or here, but caught above).
            # Specifically, if it is in global_used_ids but NOT in used_photo_ids (this step),
            # it means ANOTHER step is using it.
            # So we treat it as "Moved Away" -> Do not rescue.
            continue
        orphans.append(p)

    if orphans:
        logger.warning(
            "Step %s has %d orphan photos: %s", step_id, len(orphans), [p.id for p in orphans]
        )
        if not pages:
            pages.append([])
        # Prepend orphans to the first page
        pages[0] = orphans + pages[0]


def _get_step_photo_dir(trip_dir: Path, step: Step) -> Path | None:
    photo_dir = trip_dir / step.dir_name / "photos"
    if photo_dir.exists():
        return photo_dir

    return None
