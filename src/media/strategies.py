"""Layout strategies for photo bin-packing."""

from abc import ABC, abstractmethod

from src.data.models import PhotoWithDims


class LayoutStrategy(ABC):
    """Abstract base class for layout strategies."""

    @property
    @abstractmethod
    def required_count(self) -> int:
        """Number of photos required for this strategy."""

    @abstractmethod
    def validate_combo(self, combo: tuple[PhotoWithDims, ...]) -> bool:
        """Validate if a specific combination of photos fits this strategy."""

    def sort_combo(self, combo: tuple[PhotoWithDims, ...]) -> list[PhotoWithDims]:
        """Sort the combination according to the strategy's requirements.

        Default implementation returns the combo as a list.
        Override if specific sorting is needed.
        """
        return list(combo)


class OnePortraitTwoLandscapesStrategy(LayoutStrategy):
    @property
    def required_count(self) -> int:
        return 3

    def validate_combo(self, combo: tuple[PhotoWithDims, ...]) -> bool:
        return sum(photo.aspect_ratio < 1 for photo in combo) == 1

    def sort_combo(self, combo: tuple[PhotoWithDims, ...]) -> list[PhotoWithDims]:
        # portrait first, then landscapes
        return sorted(
            combo,
            key=lambda p: p.aspect_ratio,
        )


class ThreePortraitsStrategy(LayoutStrategy):
    @property
    def required_count(self) -> int:
        return 3

    def validate_combo(self, combo: tuple[PhotoWithDims, ...]) -> bool:
        return all(photo.aspect_ratio < 1 for photo in combo)


class FourLandscapesStrategy(LayoutStrategy):
    @property
    def required_count(self) -> int:
        return 4

    def validate_combo(self, combo: tuple[PhotoWithDims, ...]) -> bool:
        return all(photo.aspect_ratio > 1 for photo in combo)


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
