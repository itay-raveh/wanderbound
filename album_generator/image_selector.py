"""Select and manage photos for steps based on aspect ratio and quality."""

from enum import Enum
from itertools import combinations
from pathlib import Path

from PIL import Image

from .logger import get_logger
from .models import Photo
from .settings import get_settings

logger = get_logger(__name__)


class PhotoRatio(Enum):
    """Photo aspect ratio categories."""

    PORTRAIT = [(4, 5), (9, 16), (3, 4)]  # 4:5 (5:4 portrait) is ideal for cover photos
    LANDSCAPE = [(16, 9), (4, 3)]
    UNKNOWN = None  # Sentinel value


def get_photo_ratio(width: int, height: int) -> PhotoRatio:
    """Get photo ratio category."""
    aspect_ratio = width / height if height > 0 else 0

    for photo_ratio in PhotoRatio:
        if photo_ratio == PhotoRatio.UNKNOWN:
            continue
        ratio_list = (
            list(photo_ratio.value)
            if isinstance(photo_ratio.value, tuple)
            else photo_ratio.value
        )
        for ratio_tuple in ratio_list:
            ratio_width, ratio_height = ratio_tuple
            target_ratio = ratio_width / ratio_height
            if abs(aspect_ratio - target_ratio) < 0.1:
                return photo_ratio

    return PhotoRatio.UNKNOWN


def load_step_photos(photo_dir: Path) -> list[Photo]:
    """Load all photos from a step's photo directory.

    Args:
        photo_dir: Directory containing photos for a step

    Returns:
        List of Photo objects sorted by filename
    """
    if not photo_dir.exists():
        return []

    image_files = (
        sorted(photo_dir.glob("*.jpg"))
        + sorted(photo_dir.glob("*.jpeg"))
        + sorted(photo_dir.glob("*.png"))
    )

    photos: list[Photo] = []
    for index, img_path in enumerate(image_files, start=1):
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                aspect_ratio = width / height if height > 0 else 0

                photo = Photo(
                    id=img_path.name,
                    index=index,
                    path=img_path,
                    width=width,
                    height=height,
                    aspect_ratio=aspect_ratio,
                )
                photos.append(photo)
        except Exception as e:
            logger.debug(f"Error processing image {img_path}: {e}")
            continue

    return photos


def should_use_cover_photo(description: str | None) -> bool:
    """Determine if cover photo should be used based on description length.

    Args:
        description: Step description text or None

    Returns:
        True if cover photo should be used (description is None or short)
    """
    settings = get_settings()
    return (
        not description or len(description) < settings.description_max_char_cover_photo
    )


def select_cover_photo(photos: list[Photo]) -> Photo | None:
    """Select the best photo for cover based on aspect ratio and quality.

    Prioritizes 4:5 portrait photos, then other portrait photos (which can be cropped
    to 5:4), and only then landscape photos.

    Args:
        photos: List of Photo objects to choose from

    Returns:
        Best Photo for cover, or None if no photos available
    """
    if not photos:
        return None

    # Prefer 4:5 portrait (ideal for cover)
    for photo in photos:
        if photo.aspect_ratio and abs(photo.aspect_ratio - (4 / 5)) < 0.1:
            ratio = get_photo_ratio(photo.width or 0, photo.height or 0)
            if ratio == PhotoRatio.PORTRAIT:
                return photo

    # Then any other portrait (can be cropped to 5:4)
    for photo in photos:
        ratio = get_photo_ratio(photo.width or 0, photo.height or 0)
        if ratio == PhotoRatio.PORTRAIT:
            return photo

    # Finally, landscape (last resort)
    for photo in photos:
        ratio = get_photo_ratio(photo.width or 0, photo.height or 0)
        if ratio == PhotoRatio.LANDSCAPE:
            return photo

    # Last resort: any photo (prefer portrait orientation)
    for photo in photos:
        if photo.width and photo.height and photo.height > photo.width:
            return photo

    # Final fallback: first photo
    return photos[0] if photos else None


# CSS Grid layout definitions matching album.html template
# Format: (columns_fr, rows_fr, first_photo_row_span)
# These match the actual CSS grid-template-columns and grid-template-rows in album.html
_GRID_LAYOUTS: dict[int, tuple[list[float], list[float], int]] = {
    1: ([1.0], [1.0], 1),
    2: ([1.0, 1.0], [1.0], 1),
    3: ([1.0, 1.0], [1.0, 1.0], 2),  # First photo spans 2 rows
    4: ([1.0, 1.0], [1.0, 1.0], 1),
    5: ([2.0, 1.0, 1.0], [1.0, 1.0], 2),  # First photo spans 2 rows
    6: ([2.0, 1.0, 1.0], [1.0, 1.0, 1.0], 3),  # First photo spans 3 rows
}


def _calculate_photo_area_percent(photo_count: int, photo_index: int) -> float:
    """Calculate what percentage of page area a photo would occupy in a layout.

    Calculates based on actual CSS grid layouts defined in album.html template.
    Formula: Area = (column_span / total_columns) * (row_span / total_rows)

    Args:
        photo_count: Total number of photos on the page
        photo_index: Index of this photo (0-based)

    Returns:
        Percentage of page area (0-100)
    """
    if photo_count == 1:
        return 100.0

    # Use predefined grid layouts for known configurations
    if photo_count in _GRID_LAYOUTS:
        columns_fr, rows_fr, first_row_span = _GRID_LAYOUTS[photo_count]
        total_columns = sum(columns_fr)
        total_rows = sum(rows_fr)

        if photo_index == 0:
            # First photo: spans first column and multiple rows
            column_span = columns_fr[0]
            row_span = first_row_span
        else:
            # Other photos: placed in remaining columns/rows
            # For layouts with first photo spanning rows, other photos fill remaining cells
            # Calculate which column and row this photo occupies
            cells_per_row = (
                len(columns_fr) - 1
            )  # Exclude first column (used by first photo)

            if cells_per_row == 0:
                # Only one column available (shouldn't happen with our layouts)
                column_span = columns_fr[0] if len(columns_fr) > 0 else 1.0
            else:
                # Photo is in one of the remaining columns
                col_index = ((photo_index - 1) % cells_per_row) + 1
                column_span = columns_fr[col_index]

            row_span = 1

        area_percent = (column_span / total_columns) * (row_span / total_rows) * 100.0
        return round(area_percent, 1)

    # For more than 6 photos, estimate conservatively
    # Assume worst case: all photos share space equally
    return round(100.0 / photo_count, 1)


def _validate_photo_combination(photo_count: int, min_size_percent: float) -> bool:
    """Check if a photo combination respects the minimum size constraint.

    Args:
        photo_count: Number of photos in the combination
        min_size_percent: Minimum percentage of page area each photo must occupy

    Returns:
        True if all photos in this combination would be above minimum size
    """
    return all(
        _calculate_photo_area_percent(photo_count, i) >= min_size_percent
        for i in range(photo_count)
    )


# Maximum photos to test when finding valid combinations
_MAX_PHOTOS_TO_TEST = 9


def _get_max_photos_for_page(min_size_percent: float) -> int:
    """Calculate maximum number of photos that can fit on a page while respecting min size.

    Args:
        min_size_percent: Minimum percentage of page area each photo must occupy

    Returns:
        Maximum number of photos that can fit
    """
    # Test each photo count to find the maximum valid count
    for count in range(1, _MAX_PHOTOS_TO_TEST + 1):
        if not _validate_photo_combination(count, min_size_percent):
            return count - 1
    return _MAX_PHOTOS_TO_TEST


def _calculate_total_coverage(photo_count: int) -> float:
    """Calculate total page coverage for a given number of photos.

    Args:
        photo_count: Number of photos on the page

    Returns:
        Total coverage percentage (may exceed 100% due to layout constraints)
    """
    return sum(
        _calculate_photo_area_percent(photo_count, i) for i in range(photo_count)
    )


def _find_best_photo_combination(
    candidates: list[Photo], max_count: int, min_size_percent: float
) -> list[Photo]:
    """Find the best combination of photos that maximizes coverage while respecting constraints.

    Uses a combination-based approach: tries all valid combinations from largest to smallest,
    selecting the one with maximum coverage. This ensures optimal packing while respecting
    the minimum size constraint.

    Args:
        candidates: Available photos to choose from
        max_count: Maximum number of photos to include
        min_size_percent: Minimum percentage of page area each photo must occupy

    Returns:
        Best combination of photos, or empty list if no valid combination exists
    """
    if not candidates:
        return []

    # Limit max_count to available candidates
    max_count = min(max_count, len(candidates))

    best_combination: list[Photo] = []
    best_coverage = 0.0
    best_has_portrait_first = False

    # For layouts where first photo spans rows, check if we have portrait photos available
    layouts_with_portrait_preference = (3, 5, 6)
    has_portrait_photos = any(
        get_photo_ratio(p.width or 0, p.height or 0) == PhotoRatio.PORTRAIT
        for p in candidates
    )

    # Try combinations from largest to smallest (greedy: prefer more photos)
    for count in range(max_count, 0, -1):
        # Skip if this count doesn't respect minimum size
        if not _validate_photo_combination(count, min_size_percent):
            continue

        # For layouts where first photo spans rows, prefer portrait for first position
        prefer_portrait_first = (
            count in layouts_with_portrait_preference and has_portrait_photos
        )

        # Try all combinations of this size
        for combo in combinations(candidates, count):
            # Check if first photo is portrait (if we prefer it)
            has_portrait_first = False
            if prefer_portrait_first:
                first_photo = combo[0]
                first_ratio = get_photo_ratio(
                    first_photo.width or 0, first_photo.height or 0
                )
                has_portrait_first = first_ratio == PhotoRatio.PORTRAIT

            # Calculate total coverage for this combination
            total_coverage = _calculate_total_coverage(count)

            # Prefer combinations with portrait first if we're looking for that
            # But only if we haven't found a better combination yet, or if this one
            # also has portrait first and better/equal coverage
            should_update = False
            if prefer_portrait_first:
                # If we already have a combination with portrait first, only update
                # if this one also has portrait first and better coverage
                if best_has_portrait_first:
                    if has_portrait_first and total_coverage > best_coverage:
                        should_update = True
                # If we don't have one with portrait first yet, prefer this one
                # If no portrait first found yet, accept any combination
                elif has_portrait_first or not best_combination:
                    should_update = True
            else:
                # No preference, just use best coverage
                if total_coverage > best_coverage:
                    should_update = True

            if should_update:
                best_coverage = total_coverage
                best_combination = list(combo)
                best_has_portrait_first = has_portrait_first

        # Early termination: if we found a valid combination, use it
        # (greedy approach: prefer larger combinations)
        if best_combination:
            break

    return best_combination


def compute_default_photos_by_pages(
    photos: list[Photo], cover_photo: Photo | None
) -> list[list[Photo]]:
    """Compute default photo page layout using optimized bin-packing algorithm.

    Strategy:
    1. All photos (except cover) are processed through the bin-packing algorithm
    2. Priorities (in order):
       - No photo smaller than MIN_PHOTO_SIZE_PERCENT
       - Maximize page coverage
       - Minimize total pages

    Uses a combination-based approach to find optimal photo groupings. The algorithm
    tries all valid combinations from largest to smallest, selecting the one with
    maximum coverage for each page.

    Args:
        photos: List of all Photo objects for the step
        cover_photo: Cover photo to exclude from pages (or None)

    Returns:
        List of photo pages, where each page is a list of Photo objects
    """
    # Filter out cover photo
    candidates = [p for p in photos if p != cover_photo]

    if not candidates:
        return []

    photos_by_pages: list[list[Photo]] = []
    remaining = candidates.copy()
    settings = get_settings()

    # Calculate maximum photos per page based on min size constraint
    max_photos_per_page = _get_max_photos_for_page(settings.min_photo_size_percent)

    # Pack photos into pages using bin-packing algorithm
    while remaining:
        # Find the best combination of photos for this page
        best_combo = _find_best_photo_combination(
            remaining, max_photos_per_page, settings.min_photo_size_percent
        )

        if best_combo:
            photos_by_pages.append(best_combo)
            # Remove used photos from remaining
            for photo in best_combo:
                remaining.remove(photo)
        else:
            # Fallback: if no valid combination found, add single photo
            # This should only happen if min_size_percent is unreasonably high
            photos_by_pages.append([remaining.pop(0)])

    return photos_by_pages


def select_step_image(photo_dir: Path) -> Path | None:
    """Select the best image for a step based on aspect ratio (legacy function).

    This function is kept for backward compatibility. New code should use
    load_step_photos() and select_cover_photo() instead.

    Args:
        photo_dir: Directory containing photos

    Returns:
        Path to selected image, or None if no suitable image found
    """
    photos = load_step_photos(photo_dir)
    cover_photo = select_cover_photo(photos)
    return cover_photo.path if cover_photo else None
