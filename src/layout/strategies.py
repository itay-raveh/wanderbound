"""Layout strategies for photo bin-packing."""

from abc import ABC, abstractmethod
from collections.abc import Iterable

from src.data.layout import Photo, SpecialLayoutClass


class LayoutStrategy(ABC):
    """Abstract base class for layout strategies."""

    @property
    @abstractmethod
    def required_count(self) -> int:
        """Number of photos required for this strategy."""

    @property
    def layout_class(self) -> SpecialLayoutClass | None:
        return None

    def grid_style(self, photos: Iterable[Photo]) -> str | None:  # noqa: ARG002  # pyright: ignore[reportUnusedParameter]
        return None

    @abstractmethod
    def validate(self, photos: Iterable[Photo]) -> bool:
        """Validate if a specific combination of photos fits this strategy."""

    def sort(self, photos: Iterable[Photo]) -> list[Photo]:
        """Sort the combination according to the strategy's requirements.

        Default implementation returns the photos as a list.
        Override if specific sorting is needed.
        """
        return list(photos)


class OnePortraitTwoLandscapesStrategy(LayoutStrategy):
    @property
    def required_count(self) -> int:
        return 3

    @property
    def layout_class(self) -> SpecialLayoutClass | None:
        return "one-portrait-two-landscapes"

    # TODO(itay): make this better
    def grid_style(self, photos: Iterable[Photo]) -> str | None:
        p, l1, l2 = photos
        page_content_width_mm = 272
        row_gap_mm = 7
        ar_l_avg = (l1.aspect_ratio + l2.aspect_ratio) / 2
        numerator = (2 * page_content_width_mm / ar_l_avg) + row_gap_mm
        denominator = (1 / p.aspect_ratio) + (2 / ar_l_avg)
        w_p = numerator / denominator
        w_l = page_content_width_mm - w_p
        return f"grid-template-columns: {w_p}fr {w_l}fr;"

    def validate(self, photos: Iterable[Photo]) -> bool:
        return sum(photo.aspect_ratio < 1 for photo in photos) == 1

    def sort(self, photos: Iterable[Photo]) -> list[Photo]:
        # portrait first, then landscapes
        return sorted(
            photos,
            key=lambda p: p.aspect_ratio,
        )


class ThreePortraitsStrategy(LayoutStrategy):
    @property
    def required_count(self) -> int:
        return 3

    @property
    def layout_class(self) -> SpecialLayoutClass | None:
        return "three-portraits"

    def validate(self, photos: Iterable[Photo]) -> bool:
        return all(photo.aspect_ratio < 1 for photo in photos)


class FourLandscapesStrategy(LayoutStrategy):
    @property
    def required_count(self) -> int:
        return 4

    def validate(self, photos: Iterable[Photo]) -> bool:
        return all(photo.aspect_ratio > 1 for photo in photos)


class TwoPortraitsStrategy(ThreePortraitsStrategy):
    @property
    def required_count(self) -> int:
        return 2


class ThreeLandscapesStrategy(FourLandscapesStrategy):
    @property
    def required_count(self) -> int:
        return 3


class OneLandscapeStrategy(ThreeLandscapesStrategy):
    @property
    def required_count(self) -> int:
        return 1
