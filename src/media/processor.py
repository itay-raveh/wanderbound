"""Photo processing and layout computation for steps."""

from pathlib import Path

from PIL import Image, ImageOps

from src.core.logger import get_logger
from src.core.settings import settings
from src.data.layout import StepLayout
from src.data.models import PhotoWithDims, Step

from .scorer import compute_ideal_pages

logger = get_logger(__name__)


def process_step_photos(
    step: Step,
    trip_dir: Path,
    global_used_ids: set[Path],
    layout: StepLayout | None = None,
) -> tuple[list[PhotoWithDims], Path, list[list[PhotoWithDims]], list[Path]]:
    """Process photos for a single step, including loading, selection, and layout.

    Args:
        step: The step data.
        trip_dir: Path to the trip directory.
        global_used_ids: Set of photo IDs used in other steps (to prevent orphans).
        layout: Optional manual layout configuration.

    Returns:
        tuple: (all_photos, cover_photo, pages, hidden_photos)
    """
    photo_dir = trip_dir / step.dir_name / "photos"

    photos = list(map(_load_photo, photo_dir.iterdir()))

    if layout:
        # noinspection PyTypeChecker
        return *_apply_manual_layout(step, photos, layout, global_used_ids), layout.hidden_photos  # ty:ignore[invalid-return-type]

    # Determine cover photo (always select one if candidates exist, for map usage)
    cover_photo = _select_cover(photos)

    pages = compute_ideal_pages(
        photos,
        (
            cover_photo
            if len(step.description) <= settings.description_two_columns_threshold
            else None
        ),
    )

    return photos, cover_photo.path, pages, []


def _apply_manual_layout(
    step: Step,
    local_photos: list[PhotoWithDims],
    layout: StepLayout,
    global_used_photos: set[Path],
) -> tuple[list[PhotoWithDims], Path, list[list[PhotoWithDims]]]:
    photo_map = {p.path: p for p in local_photos}

    all_needed_paths = set[Path]()
    if layout.cover_photo:
        all_needed_paths.add(layout.cover_photo)
    all_needed_paths.update(layout.hidden_photos)
    for page in layout.pages:
        all_needed_paths.update(page.photos)

    for path in all_needed_paths:
        if path not in photo_map:
            photo_map[path] = _load_photo(path)

    used_photos = set(layout.hidden_photos)
    if layout.cover_photo and len(step.description) <= settings.description_two_columns_threshold:
        used_photos.add(layout.cover_photo)

    pages = _build_pages(layout, photo_map, used_photos)

    if orphans := {p1.path for p1 in local_photos} - used_photos - global_used_photos:
        logger.warning("Step %s has %d orphan photos: %s", layout.id, len(orphans), orphans)
        pages.append(list(map(_load_photo, orphans)))

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


def _load_photo(img_path: Path) -> PhotoWithDims:
    with Image.open(img_path) as img:
        img_rotated = ImageOps.exif_transpose(img)
        width, height = img_rotated.size

    return PhotoWithDims(
        path=img_path.absolute(),
        width=width,
        height=height,
    )


def _select_cover(photos: list[PhotoWithDims]) -> PhotoWithDims:
    portraits = [p for p in photos if p.aspect_ratio < 1]
    if portraits:
        return portraits[0]

    return photos[0]
