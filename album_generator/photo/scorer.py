"""Photo scoring and bin-packing algorithms for page layout."""

from itertools import combinations

from ..logger import get_logger
from ..models import Photo
from ..settings import get_settings
from .layout import _is_one_portrait_two_landscapes, _is_three_portraits
from .ratio import PhotoRatio, get_photo_ratio

logger = get_logger(__name__)

__all__ = [
    "_calculate_photo_area_percent",
    "_validate_photo_combination",
    "_get_max_photos_for_page",
    "_calculate_total_coverage",
    "_calculate_visual_score",
    "_find_best_photo_combination",
    "compute_default_photos_by_pages",
]

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


def _calculate_photo_area_percent(
    photo_count: int,
    photo_index: int,
    is_three_portraits: bool = False,
    is_portrait_landscape_split: bool = False,
) -> float:
    """Calculate what percentage of page area a photo would occupy in a layout.

    Calculates based on actual CSS grid layouts defined in album.html template.
    Formula: Area = (column_span / total_columns) * (row_span / total_rows)

    Args:
        photo_count: Total number of photos on the page
        photo_index: Index of this photo (0-based)
        is_three_portraits: If True, use 3-portrait side-by-side layout
        is_portrait_landscape_split: If True, use portrait-left, landscapes-right stacked layout

    Returns:
        Percentage of page area (0-100)
    """
    settings = get_settings()
    if photo_count == 1:
        return settings.photo.photo_area_full_page

    # Special case: 3 portraits side by side
    if photo_count == settings.photo.photo_count_for_special_layouts and is_three_portraits:
        # 3 equal columns, 1 row
        return round(settings.photo.photo_area_three_portraits, 1)

    # Special case: 1 portrait + 2 landscapes (portrait on left, landscapes stacked on right)
    if (
        photo_count == settings.photo.photo_count_for_special_layouts
        and is_portrait_landscape_split
    ):
        if photo_index == 0:
            # Portrait on left: takes 50% of width, 100% of height
            return settings.photo.photo_area_portrait_left
        else:
            # Landscapes on right: each takes 50% of width, 50% of height
            return settings.photo.photo_area_landscape_right

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
            cells_per_row = len(columns_fr) - 1  # Exclude first column (used by first photo)

            if cells_per_row == 0:
                # Only one column available (shouldn't happen with our layouts)
                column_span = columns_fr[0] if len(columns_fr) > 0 else 1.0
            else:
                # Photo is in one of the remaining columns
                col_index = ((photo_index - 1) % cells_per_row) + 1
                column_span = columns_fr[col_index]

            row_span = 1

        settings = get_settings()
        area_percent = (
            (column_span / total_columns)
            * (row_span / total_rows)
            * settings.photo.photo_area_full_page
        )
        return round(area_percent, 1)

    # For more than 6 photos, estimate conservatively
    # Assume worst case: all photos share space equally
    settings = get_settings()
    return round(settings.photo.photo_area_full_page / photo_count, 1)


def _validate_photo_combination(
    photo_count: int,
    min_size_percent: float,
    is_three_portraits: bool = False,
    is_portrait_landscape_split: bool = False,
) -> bool:
    """Check if a photo combination respects the minimum size constraint.

    Args:
        photo_count: Number of photos in the combination
        min_size_percent: Minimum percentage of page area each photo must occupy
        is_three_portraits: If True, use 3-portrait side-by-side layout
        is_portrait_landscape_split: If True, use portrait-landscape split layout

    Returns:
        True if all photos in this combination would be above minimum size
    """
    return all(
        _calculate_photo_area_percent(
            photo_count, i, is_three_portraits, is_portrait_landscape_split
        )
        >= min_size_percent
        for i in range(photo_count)
    )


def _get_max_photos_for_page(min_size_percent: float) -> int:
    """Calculate maximum number of photos that can fit on a page while respecting min size.

    Args:
        min_size_percent: Minimum percentage of page area each photo must occupy

    Returns:
        Maximum number of photos that can fit
    """
    # Test each photo count to find the maximum valid count
    # Check both regular and 3-portrait layouts for count 3
    settings = get_settings()
    for count in range(1, settings.photo.max_photos_to_test + 1):
        if count == settings.photo.photo_count_for_special_layouts:
            # For 3 photos, check both layouts
            if not _validate_photo_combination(
                count, min_size_percent, False, False
            ) and not _validate_photo_combination(count, min_size_percent, True, False):
                return count - 1
        else:
            if not _validate_photo_combination(count, min_size_percent, False, False):
                return count - 1
    settings = get_settings()
    return settings.photo.max_photos_to_test


def _calculate_total_coverage(
    photo_count: int,
    is_three_portraits: bool = False,
    is_portrait_landscape_split: bool = False,
) -> float:
    """Calculate total page coverage for a given number of photos.

    Args:
        photo_count: Number of photos on the page
        is_three_portraits: If True, use 3-portrait side-by-side layout
        is_portrait_landscape_split: If True, use portrait-landscape split layout

    Returns:
        Total coverage percentage (may exceed 100% due to layout constraints)
    """
    return sum(
        _calculate_photo_area_percent(
            photo_count, i, is_three_portraits, is_portrait_landscape_split
        )
        for i in range(photo_count)
    )


def _calculate_visual_score(combo: tuple[Photo, ...], count: int) -> float:
    """Calculate a visual balance score for a photo combination.

    Higher scores indicate better visual balance:
    - Large bonus for 3 portraits side by side (special layout)
    - Prefers portrait photos in first position for multi-row layouts (5, 6 photos)

    Args:
        combo: Photo combination to score
        count: Number of photos in the combination

    Returns:
        Visual score (higher is better)
    """
    settings = get_settings()
    score = 0.0

    # Large bonus for 3 portraits side by side (special layout)
    if _is_three_portraits(combo):
        score += settings.photo.score_three_portraits_bonus

    # For multi-row layouts (5, 6 photos), prefer portrait in first position
    # Note: 3 photos with portrait first is handled by the 3-portrait layout above
    if count in settings.photo.multi_row_layout_counts and combo:
        first_photo = combo[0]
        first_ratio = get_photo_ratio(first_photo.width or 0, first_photo.height or 0)
        if first_ratio == PhotoRatio.PORTRAIT:
            score += settings.photo.score_portrait_first_bonus

    return score


def _find_best_photo_combination(
    candidates: list[Photo], max_count: int, min_size_percent: float
) -> tuple[list[Photo], bool, bool]:
    """Find the best combination of photos using refined priority system.

    Priorities (in order):
    1. Respect minimum size constraint (hard requirement)
    2. Maximize number of photos per page (within size constraints)
    3. Maximize page coverage (fill as much space as possible)
    4. Visual balance (portrait preference, aspect ratio diversity)

    Evaluates all valid combinations to find the truly optimal one, rather than
    using early termination.

    Args:
        candidates: Available photos to choose from
        max_count: Maximum number of photos to include
        min_size_percent: Minimum percentage of page area each photo must occupy

    Returns:
        Tuple of (best combination of photos, is_three_portraits flag, is_portrait_landscape_split flag)
        Returns (empty list, False, False) if no valid combination exists
    """
    if not candidates:
        return [], False, False

    # Limit max_count to available candidates
    max_count = min(max_count, len(candidates))

    best_combination: list[Photo] = []
    best_score = -1.0
    best_is_three_portraits = False
    best_is_portrait_landscape_split = False

    # Evaluate all valid combinations across all counts
    # We'll score them: (photo_count * 1000) + coverage + visual_score
    # This ensures priority 2 (more photos) > priority 3 (coverage) > priority 4 (visual)
    for count in range(max_count, 0, -1):
        # Check all special layouts for count 3
        settings = get_settings()
        layouts_to_check = []
        if count == settings.photo.photo_count_for_special_layouts:
            layouts_to_check = [
                (True, False, "three_portraits"),
                (False, True, "portrait_landscape_split"),
                (False, False, "default"),
            ]
        else:
            layouts_to_check = [(False, False, "default")]

        for (
            is_three_portraits,
            is_portrait_landscape_split,
            _layout_name,
        ) in layouts_to_check:
            # Skip if this layout doesn't respect minimum size
            if not _validate_photo_combination(
                count, min_size_percent, is_three_portraits, is_portrait_landscape_split
            ):
                continue

            # Try all combinations of this size
            for combo in combinations(candidates, count):
                # For 3-portrait layout, only consider if all are portraits
                if is_three_portraits and not _is_three_portraits(combo):
                    continue

                # For portrait-landscape split layout, only consider if 1 portrait + 2 landscapes
                if is_portrait_landscape_split and not _is_one_portrait_two_landscapes(combo):
                    continue

                # Calculate total coverage for this combination
                total_coverage = _calculate_total_coverage(
                    count, is_three_portraits, is_portrait_landscape_split
                )

                # Calculate visual balance score
                visual_score = _calculate_visual_score(combo, count)

                # Combined score: prioritize photo count, then coverage, then visual
                # Use large multiplier for count to ensure it's the primary factor
                settings = get_settings()
                layout_bonus = 0.0

                if is_three_portraits and _is_three_portraits(combo):
                    # Bonus must be >10000 to overcome the difference between 3 and 4 photos
                    # (4 photos = 40000 base, 3 photos = 30000 base, difference = 10000)
                    layout_bonus = settings.photo.score_layout_bonus_three_portraits

                    # Extra bonus if all 3 portraits have the same aspect ratio (more uniform)
                    if len(combo) == settings.photo.photo_count_for_special_layouts:
                        aspect_ratios = [
                            ((p.width or 0) / (p.height or 1) if (p.height or 0) > 0 else 0)
                            for p in combo
                        ]
                        # Check if all aspect ratios are approximately the same
                        rounded_ratios = {round(ar, 2) for ar in aspect_ratios}
                        if len(rounded_ratios) == 1:
                            layout_bonus += settings.photo.score_uniform_aspect_ratio_bonus

                elif is_portrait_landscape_split and _is_one_portrait_two_landscapes(combo):
                    # Bonus for portrait-landscape split layout (prefer over default 3-photo layout)
                    layout_bonus = settings.photo.score_portrait_landscape_split_bonus

                score = (
                    (count * settings.photo.score_photo_count_multiplier)
                    + total_coverage
                    + visual_score
                    + layout_bonus
                )

                if score > best_score:
                    best_score = score
                    # For portrait-landscape split, ensure portrait is first (left side)
                    if is_portrait_landscape_split and _is_one_portrait_two_landscapes(combo):
                        # Sort: portrait first, then landscapes
                        sorted_combo = sorted(
                            combo,
                            key=lambda p: (
                                0
                                if get_photo_ratio(p.width or 0, p.height or 0)
                                == PhotoRatio.PORTRAIT
                                else 1
                            ),
                        )
                        best_combination = list(sorted_combo)
                    else:
                        best_combination = list(combo)
                    best_is_three_portraits = is_three_portraits
                    best_is_portrait_landscape_split = is_portrait_landscape_split

    return best_combination, best_is_three_portraits, best_is_portrait_landscape_split


def compute_default_photos_by_pages(
    photos: list[Photo], cover_photo: Photo | None
) -> tuple[list[list[Photo]], list[bool], list[bool]]:
    """Compute default photo page layout using optimized bin-packing algorithm.

    Strategy:
    1. All photos (except cover) are processed through the bin-packing algorithm
    2. Priorities (in order):
       a. Respect minimum size constraint (hard requirement - no photo < MIN_PHOTO_SIZE_PERCENT)
       b. Maximize number of photos per page (within size constraints)
       c. Maximize page coverage (fill as much space as possible)
       d. Visual balance (prefer portrait in first position for multi-row layouts, aspect ratio diversity)
       e. Minimize total pages (byproduct of maximizing per-page efficiency)

    Uses a combination-based approach that evaluates all valid combinations to find
    the truly optimal one, rather than using greedy early termination.

    Args:
        photos: List of all Photo objects for the step
        cover_photo: Cover photo to exclude from pages (or None)

    Returns:
        Tuple of (list of photo pages, list of is_three_portraits flags, list of is_portrait_landscape_split flags)
        Each page is a list of Photo objects, and flags indicate which layout to use
    """
    # Filter out cover photo
    candidates = [p for p in photos if p != cover_photo]

    if not candidates:
        return [], [], []

    photos_by_pages: list[list[Photo]] = []
    is_three_portraits_flags: list[bool] = []
    is_portrait_landscape_split_flags: list[bool] = []
    remaining = candidates.copy()
    settings = get_settings()

    # Calculate maximum photos per page based on min size constraint
    max_photos_per_page = _get_max_photos_for_page(settings.min_photo_size_percent)

    # Pack photos into pages using bin-packing algorithm
    while remaining:
        # Find the best combination of photos for this page
        best_combo, is_three_portraits, is_portrait_landscape_split = _find_best_photo_combination(
            remaining, max_photos_per_page, settings.min_photo_size_percent
        )

        if best_combo:
            # ALWAYS force correct layout if we have matching photos, regardless of algorithm choice
            settings = get_settings()
            if len(best_combo) == settings.photo.photo_count_for_special_layouts:
                is_three_portraits_forced = _is_three_portraits(tuple(best_combo))
                is_portrait_landscape_split_forced = _is_one_portrait_two_landscapes(
                    tuple(best_combo)
                )
                if is_three_portraits_forced:
                    is_three_portraits = True
                    is_portrait_landscape_split = False
                    logger.debug("FORCING 3-portrait layout for page with 3 portrait photos")
                elif is_portrait_landscape_split_forced:
                    is_three_portraits = False
                    is_portrait_landscape_split = True
                    logger.debug(
                        "FORCING portrait-landscape split layout for page with 1 portrait + 2 landscapes"
                    )
                else:
                    # Check what we actually have
                    ratios = [get_photo_ratio(p.width or 0, p.height or 0) for p in best_combo]
                    logger.debug(
                        f"Page with 3 photos but no special layout detected. Ratios: {[r.name for r in ratios]}"
                    )
            photos_by_pages.append(best_combo)
            is_three_portraits_flags.append(is_three_portraits)
            is_portrait_landscape_split_flags.append(is_portrait_landscape_split)
            ratios = [get_photo_ratio(p.width or 0, p.height or 0) for p in best_combo]
            logger.debug(
                f"Page with {len(best_combo)} photos, is_three_portraits={is_three_portraits}, "
                f"is_portrait_landscape_split={is_portrait_landscape_split}, "
                f"photo ratios: {[r.name for r in ratios]}, "
                f"dimensions: {[(p.width, p.height) for p in best_combo]}"
            )
            # Remove used photos from remaining
            for photo in best_combo:
                remaining.remove(photo)
        else:
            # Fallback: if no valid combination found, add single photo
            # This should only happen if min_size_percent is unreasonably high
            photos_by_pages.append([remaining.pop(0)])
            is_three_portraits_flags.append(False)
            is_portrait_landscape_split_flags.append(False)

    return photos_by_pages, is_three_portraits_flags, is_portrait_landscape_split_flags
