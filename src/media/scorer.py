"""Photo scoring and bin-packing algorithms for page layout."""

from collections.abc import Sequence
from itertools import combinations

from src.core.logger import get_logger
from src.data.models import PhotoWithDims

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
    candidates: Sequence[PhotoWithDims], strategies: list[LayoutStrategy]
) -> list[PhotoWithDims] | None:
    for strategy in strategies:
        if strategy.required_count > len(candidates):
            continue

        for combo in combinations(candidates, strategy.required_count):
            if strategy.validate_combo(combo):
                return strategy.sort_combo(combo)
    return None


def _find_best_photo_combination(candidates: Sequence[PhotoWithDims]) -> list[PhotoWithDims]:
    if not candidates:
        return []

    if result := _try_strategies(candidates, _GOOD_STRATEGIES):
        return result

    if result := _try_strategies(candidates, _ACCEPTABLE_STRATEGIES):
        return result

    return [candidates[0]]


def compute_ideal_pages(
    photos: list[PhotoWithDims], cover_photo: PhotoWithDims | None
) -> list[list[PhotoWithDims]]:
    candidates = set(photos)

    if cover_photo:
        candidates.remove(cover_photo)

    pages: list[list[PhotoWithDims]] = []
    while candidates:
        best_combo = _find_best_photo_combination(tuple(candidates))
        pages.append(best_combo)
        candidates -= set(best_combo)

    return pages
