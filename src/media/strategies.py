"""Layout strategies for photo bin-packing."""

from abc import ABC, abstractmethod

from src.data.models import Photo

from .layout_engine import (
    PhotoRatio,
    get_photo_ratio,
    is_one_portrait_two_landscapes,
    is_three_portraits,
)


class LayoutStrategy(ABC):
    """Abstract base class for layout strategies."""

    @property
    @abstractmethod
    def required_count(self) -> int:
        """Number of photos required for this strategy."""

    @abstractmethod
    def validate_combo(self, combo: tuple[Photo, ...]) -> bool:
        """Validate if a specific combination of photos fits this strategy."""

    def sort_combo(self, combo: tuple[Photo, ...]) -> list[Photo]:
        """Sort the combination according to the strategy's requirements.

        Default implementation returns the combo as a list.
        Override if specific sorting is needed.
        """
        return list(combo)


# --- GOOD LAYOUTS ---


class ThreePortraitsStrategy(LayoutStrategy):
    """GOOD: 3 portraits side-by-side."""

    @property
    def required_count(self) -> int:
        return 3

    def validate_combo(self, combo: tuple[Photo, ...]) -> bool:
        return is_three_portraits(combo)


class OnePortraitTwoLandscapesStrategy(LayoutStrategy):
    """GOOD: 1 portrait and 2 landscapes."""

    @property
    def required_count(self) -> int:
        return 3

    def validate_combo(self, combo: tuple[Photo, ...]) -> bool:
        return is_one_portrait_two_landscapes(combo)

    def sort_combo(self, combo: tuple[Photo, ...]) -> list[Photo]:
        # Sort: portrait first, then landscapes
        return sorted(
            combo,
            key=lambda p: (
                0 if get_photo_ratio(p.width or 0, p.height or 0) == PhotoRatio.PORTRAIT else 1
            ),
        )


class FourLandscapesStrategy(LayoutStrategy):
    """GOOD: 4 landscapes (2x2 grid)."""

    @property
    def required_count(self) -> int:
        return 4

    def validate_combo(self, combo: tuple[Photo, ...]) -> bool:
        for photo in combo:
            if get_photo_ratio(photo.width or 0, photo.height or 0) != PhotoRatio.LANDSCAPE:
                return False
        return True


# --- ACCEPTABLE LAYOUTS ---


class TwoPortraitsStrategy(LayoutStrategy):
    """ACCEPTABLE: 2 portraits side-by-side."""

    @property
    def required_count(self) -> int:
        return 2

    def validate_combo(self, combo: tuple[Photo, ...]) -> bool:
        for photo in combo:
            if get_photo_ratio(photo.width or 0, photo.height or 0) != PhotoRatio.PORTRAIT:
                return False
        return True


class ThreeLandscapesStrategy(LayoutStrategy):
    """ACCEPTABLE: 3 landscapes (1 big, 2 small stacked)."""

    @property
    def required_count(self) -> int:
        return 3

    def validate_combo(self, combo: tuple[Photo, ...]) -> bool:
        # We need 3 landscapes
        for photo in combo:
            if get_photo_ratio(photo.width or 0, photo.height or 0) != PhotoRatio.LANDSCAPE:
                return False
        return True


class OneLandscapeStrategy(LayoutStrategy):
    """ACCEPTABLE: 1 landscape (full width)."""

    @property
    def required_count(self) -> int:
        return 1

    def validate_combo(self, combo: tuple[Photo, ...]) -> bool:
        if not combo:
            return False
        return get_photo_ratio(combo[0].width or 0, combo[0].height or 0) == PhotoRatio.LANDSCAPE
