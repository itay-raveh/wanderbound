from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .media import Media


class LayoutStrategy(ABC):
    """Abstract base class for layout strategies."""

    @property
    @abstractmethod
    def required_count(self) -> int:
        """Number of photos required for this strategy."""

    @abstractmethod
    def validate(self, photos: Iterable[Media]) -> bool:
        """Validate if a specific combination of photos fits this strategy."""

    def sort(self, photos: Iterable[Media]) -> list[Media]:
        """Sort the combination according to the strategy's requirements.

        Default implementation returns the photos as a list.
        Override if specific sorting is needed.
        """
        return list(photos)


class OnePortraitTwoLandscapesStrategy(LayoutStrategy):
    @property
    def required_count(self) -> int:
        return 3

    def validate(self, photos: Iterable[Media]) -> bool:
        return sum(photo.is_portrait for photo in photos) == 1

    def sort(self, photos: Iterable[Media]) -> list[Media]:
        # portrait first, then landscapes
        return sorted(
            photos,
            key=lambda p: not p.is_portrait,
        )


class _AllPortraitsStrategy(LayoutStrategy, ABC):
    def validate(self, photos: Iterable[Media]) -> bool:
        return all(photo.is_portrait for photo in photos)


class ThreePortraitsStrategy(_AllPortraitsStrategy):
    @property
    def required_count(self) -> int:
        return 3


class TwoPortraitsStrategy(_AllPortraitsStrategy):
    @property
    def required_count(self) -> int:
        return 2


class FourLandscapesStrategy(LayoutStrategy):
    @property
    def required_count(self) -> int:
        return 4

    def validate(self, photos: Iterable[Media]) -> bool:
        return all(not photo.is_portrait for photo in photos)


class ThreeLandscapesStrategy(FourLandscapesStrategy):
    @property
    def required_count(self) -> int:
        return 3


class OneLandscapeStrategy(ThreeLandscapesStrategy):
    @property
    def required_count(self) -> int:
        return 1
