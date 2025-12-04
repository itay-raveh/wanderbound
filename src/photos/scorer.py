"""Photo scoring and bin-packing algorithms for page layout."""

from itertools import combinations

from src.core.logger import get_logger
from src.data.models import Photo

from .strategies import (
    FourLandscapesStrategy,
    LayoutStrategy,
    OneLandscapeStrategy,
    OnePortraitTwoLandscapesStrategy,
    ThreeLandscapesStrategy,
    ThreePortraitsStrategy,
    TwoPortraitsStrategy,
)

logger = get_logger(__name__)


# Instantiate strategies in order of preference
_GOOD_STRATEGIES: list[LayoutStrategy] = [
    ThreePortraitsStrategy(),
    OnePortraitTwoLandscapesStrategy(),
    FourLandscapesStrategy(),
]

_ACCEPTABLE_STRATEGIES: list[LayoutStrategy] = [
    TwoPortraitsStrategy(),
    ThreeLandscapesStrategy(),
    OneLandscapeStrategy(),
]


def _try_strategies(
    candidates: list[Photo], strategies: list[LayoutStrategy]
) -> tuple[list[Photo], bool, bool] | None:
    """Try a list of strategies and return the first valid combination found."""
    for strategy in strategies:
        count = strategy.required_count

        if count > len(candidates):
            continue

        for combo in combinations(candidates, count):
            if strategy.validate_combo(combo):
                return (
                    strategy.sort_combo(combo),
                    strategy.is_three_portraits,
                    strategy.is_portrait_landscape_split,
                )
    return None


def _find_best_photo_combination(
    candidates: list[Photo],
) -> tuple[list[Photo], bool, bool]:
    """Find the best combination of photos using strict quality rules."""
    if not candidates:
        return [], False, False

    # 1. Try GOOD layouts first
    result = _try_strategies(candidates, _GOOD_STRATEGIES)
    if result:
        return result

    # 2. Try ACCEPTABLE layouts
    result = _try_strategies(candidates, _ACCEPTABLE_STRATEGIES)
    if result:
        return result

    # 3. Fallback (should be rare if we have enough photos, but we need to handle leftovers)
    # If we can't make even an acceptable layout, just take 1 photo and hope for the best
    # (or maybe we should just take the first available photo and render it singly)
    return [candidates[0]], False, False


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

    while remaining:
        # Find the best combination of photos for this page
        best_combo, best_is_three_portraits, best_is_portrait_landscape_split = (
            _find_best_photo_combination(remaining)
        )

        photos_by_pages.append(best_combo)
        is_three_portraits_flags.append(best_is_three_portraits)
        is_portrait_landscape_split_flags.append(best_is_portrait_landscape_split)

        # Remove used photos from remaining
        for photo in best_combo:
            if photo in remaining:
                remaining.remove(photo)

    return photos_by_pages, is_three_portraits_flags, is_portrait_landscape_split_flags
