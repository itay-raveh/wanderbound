"""Photo scoring and bin-packing algorithms for page layout."""

from collections.abc import Collection, Iterable
from itertools import combinations

from src.core.logger import get_logger
from src.data.layout import PageLayout, Photo

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

# In order of preference
_STRATEGIES: list[LayoutStrategy] = [
    ThreePortraitsStrategy(),
    OnePortraitTwoLandscapesStrategy(),
    FourLandscapesStrategy(),
    TwoPortraitsStrategy(),
    ThreeLandscapesStrategy(),
    OneLandscapeStrategy(),
]


def try_choose_layout(photos: Collection[Photo]) -> PageLayout | None:
    for strategy in _STRATEGIES:
        if strategy.required_count == len(photos) and strategy.validate(photos):
            return PageLayout(photos=strategy.sort(photos), layout_class=strategy.layout_class)
    return None


def _try_build_page(candidates: Collection[Photo]) -> PageLayout | None:
    for strategy in _STRATEGIES:
        if strategy.required_count > len(candidates):
            continue

        for combo in combinations(candidates, strategy.required_count):
            if strategy.validate(combo):
                return PageLayout(
                    photos=strategy.sort(combo),
                    layout_class=strategy.layout_class,
                )
    return None


def gen_page_layouts(photos: Iterable[Photo]) -> list[PageLayout]:
    candidates = set(photos)

    # Divide photos intp pages
    pages: list[PageLayout] = []
    while candidates:
        if layout := _try_build_page(candidates):
            pages.append(layout)
            candidates -= set(layout.photos)
        else:
            # If no strategies work, give some photo its own page,
            # and we will try again with the rest
            pages.append(PageLayout(photos=[candidates.pop()], layout_class=None))

    return pages
