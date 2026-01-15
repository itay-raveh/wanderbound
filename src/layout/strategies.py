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

    def validate(self, photos: Iterable[Photo]) -> bool:
        return sum(photo.is_portrait for photo in photos) == 1

    def sort(self, photos: Iterable[Photo]) -> list[Photo]:
        # portrait first, then landscapes
        return sorted(
            photos,
            key=lambda p: not p.is_portrait,
        )


class _AllPortraitsStrategy(LayoutStrategy, ABC):
    def validate(self, photos: Iterable[Photo]) -> bool:
        return all(photo.is_portrait for photo in photos)


class ThreePortraitsStrategy(_AllPortraitsStrategy):
    @property
    def required_count(self) -> int:
        return 3

    @property
    def layout_class(self) -> SpecialLayoutClass | None:
        return "three-portraits"


class TwoPortraitsStrategy(_AllPortraitsStrategy):
    @property
    def required_count(self) -> int:
        return 2


class FourLandscapesStrategy(LayoutStrategy):
    @property
    def required_count(self) -> int:
        return 4

    def validate(self, photos: Iterable[Photo]) -> bool:
        return all(not photo.is_portrait for photo in photos)


class ThreeLandscapesStrategy(FourLandscapesStrategy):
    @property
    def required_count(self) -> int:
        return 3


class OneLandscapeStrategy(ThreeLandscapesStrategy):
    @property
    def required_count(self) -> int:
        return 1
