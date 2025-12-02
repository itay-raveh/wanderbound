"""Photo scoring and bin-packing algorithms for page layout."""

from itertools import combinations

from src.core.logger import get_logger
from src.core.settings import settings
from src.data.models import Photo

from .layout_engine import (
    get_photo_ratio,
    is_one_portrait_two_landscapes,
    is_three_portraits,
)
from .strategies import (
    DefaultLayoutStrategy,
    LayoutStrategy,
    PortraitLandscapeSplitStrategy,
    ThreePortraitsStrategy,
)

logger = get_logger(__name__)


# Instantiate strategies
_STRATEGIES: list[LayoutStrategy] = [
    ThreePortraitsStrategy(),
    PortraitLandscapeSplitStrategy(),
    DefaultLayoutStrategy(),
]


def _get_applicable_strategies(count: int) -> list[LayoutStrategy]:
    """Get applicable strategies for a given photo count."""
    return [s for s in _STRATEGIES if s.is_applicable(count)]


def _calculate_photo_area_percent(
    photo_count: int,
    photo_index: int,
    strategy: LayoutStrategy,
) -> float:
    """Calculate what percentage of page area a photo would occupy in a layout."""
    if isinstance(strategy, DefaultLayoutStrategy):
        return strategy.calculate_photo_area_percent(photo_count, photo_index)
    if isinstance(strategy, ThreePortraitsStrategy):
        return strategy.calculate_photo_area_percent(photo_count, photo_index)
    if isinstance(strategy, PortraitLandscapeSplitStrategy):
        return strategy.calculate_photo_area_percent(photo_count, photo_index)

    # Fallback (should not happen if strategies are correctly implemented)
    return round(settings.photo.photo_area_full_page / photo_count, 1)


def _validate_photo_combination(
    photo_count: int,
    min_size_percent: float,
    strategy: LayoutStrategy,
) -> bool:
    """Check if a photo combination respects the minimum size constraint."""
    return all(
        _calculate_photo_area_percent(photo_count, i, strategy) >= min_size_percent
        for i in range(photo_count)
    )


def _get_max_photos_for_page(min_size_percent: float) -> int:
    """Calculate maximum number of photos that can fit on a page while respecting min size."""
    for count in range(1, settings.photo.max_photos_to_test + 1):
        strategies = _get_applicable_strategies(count)
        # If ANY strategy works for this count, it's potentially valid.
        # But we need to find the MAX count where AT LEAST ONE strategy is valid.
        # Actually, the logic is: if NO strategy works for this count,
        # then the PREVIOUS count was the max.

        valid_strategy_found = False
        for strategy in strategies:
            if _validate_photo_combination(count, min_size_percent, strategy):
                valid_strategy_found = True
                break

        if not valid_strategy_found:
            return count - 1

    return settings.photo.max_photos_to_test


def _calculate_total_coverage(
    photo_count: int,
    strategy: LayoutStrategy,
) -> float:
    """Calculate total page coverage for a given number of photos."""
    return sum(_calculate_photo_area_percent(photo_count, i, strategy) for i in range(photo_count))


def _evaluate_combination(
    combo: tuple[Photo, ...],
    count: int,
    strategy: LayoutStrategy,
) -> float:
    """Evaluate and score a photo combination."""
    total_coverage = _calculate_total_coverage(count, strategy)
    strategy_score = strategy.calculate_score(combo, count)

    return (count * settings.photo.score_photo_count_multiplier) + total_coverage + strategy_score


def _find_best_photo_combination(
    candidates: list[Photo], max_count: int, min_size_percent: float
) -> tuple[list[Photo], bool, bool]:
    """Find the best combination of photos using refined priority system."""
    if not candidates:
        return [], False, False

    max_count = min(max_count, len(candidates))

    best_combination: list[Photo] = []
    best_score = -1.0
    best_is_three_portraits = False
    best_is_portrait_landscape_split = False

    for count in range(max_count, 0, -1):
        strategies = _get_applicable_strategies(count)

        for strategy in strategies:
            if not _validate_photo_combination(count, min_size_percent, strategy):
                continue

            for combo in combinations(candidates, count):
                if not strategy.validate_combo(combo):
                    continue

                score = _evaluate_combination(combo, count, strategy)

                if score > best_score:
                    best_score = score
                    best_combination = strategy.sort_combo(combo)
                    best_is_three_portraits = strategy.is_three_portraits
                    best_is_portrait_landscape_split = strategy.is_portrait_landscape_split

    return best_combination, best_is_three_portraits, best_is_portrait_landscape_split


def compute_default_photos_by_pages(
    photos: list[Photo], cover_photo: Photo | None
) -> tuple[list[list[Photo]], list[bool], list[bool]]:
    """Compute default photo page layout using optimized bin-packing algorithm."""
    # Filter out cover photo
    candidates = [p for p in photos if p != cover_photo]

    if not candidates:
        return [], [], []

    photos_by_pages: list[list[Photo]] = []
    is_three_portraits_flags: list[bool] = []
    is_portrait_landscape_split_flags: list[bool] = []
    remaining = candidates.copy()

    # Calculate maximum photos per page based on min size constraint
    max_photos_per_page = _get_max_photos_for_page(settings.min_photo_size_percent)

    # Pack photos into pages using bin-packing algorithm
    while remaining:
        # Find the best combination of photos for this page
        best_combo, best_is_three_portraits, best_is_portrait_landscape_split = (
            _find_best_photo_combination(
                remaining, max_photos_per_page, settings.min_photo_size_percent
            )
        )

        if best_combo:
            # ALWAYS force correct layout if we have matching photos, regardless of algorithm choice
            if len(best_combo) == settings.photo.photo_count_for_special_layouts:
                is_three_portraits_forced = is_three_portraits(tuple(best_combo))
                is_portrait_landscape_split_forced = is_one_portrait_two_landscapes(
                    tuple(best_combo)
                )
                if is_three_portraits_forced:
                    best_is_three_portraits = True
                    best_is_portrait_landscape_split = False
                    logger.debug("FORCING 3-portrait layout for page with 3 portrait photos")
                elif is_portrait_landscape_split_forced:
                    best_is_three_portraits = False
                    best_is_portrait_landscape_split = True
                    logger.debug(
                        "FORCING portrait-landscape split layout "
                        "for page with 1 portrait + 2 landscapes"
                    )
                else:
                    # Check what we actually have
                    ratios = [get_photo_ratio(p.width or 0, p.height or 0) for p in best_combo]
                    logger.debug(
                        "Page with 3 photos but no special layout detected. Ratios: %s",
                        [r.name for r in ratios],
                    )
            photos_by_pages.append(best_combo)
            is_three_portraits_flags.append(best_is_three_portraits)
            is_portrait_landscape_split_flags.append(best_is_portrait_landscape_split)
            ratios = [get_photo_ratio(p.width or 0, p.height or 0) for p in best_combo]
            logger.debug(
                "Page with %d photos, is_three_portraits=%s, "
                "is_portrait_landscape_split=%s, "
                "photo ratios: %s, dimensions: %s",
                len(best_combo),
                best_is_three_portraits,
                best_is_portrait_landscape_split,
                [r.name for r in ratios],
                [(p.width, p.height) for p in best_combo],
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
