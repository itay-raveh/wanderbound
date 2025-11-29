"""Layout strategies for photo bin-packing."""

from abc import ABC, abstractmethod
from typing import ClassVar

from src.core.settings import settings
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
    def name(self) -> str:
        """Name of the strategy."""

    @abstractmethod
    def is_applicable(self, count: int) -> bool:
        """Check if this strategy is applicable for the given photo count."""

    @abstractmethod
    def validate_combo(self, combo: tuple[Photo, ...]) -> bool:
        """Validate if a specific combination of photos fits this strategy."""

    @abstractmethod
    def calculate_score(self, combo: tuple[Photo, ...], count: int) -> float:
        """Calculate the score for a combination using this strategy."""

    @abstractmethod
    def sort_combo(self, combo: tuple[Photo, ...]) -> list[Photo]:
        """Sort the combination according to the strategy's requirements."""

    @property
    def is_three_portraits(self) -> bool:
        """Return True if this is the three portraits strategy."""
        return False

    @property
    def is_portrait_landscape_split(self) -> bool:
        """Return True if this is the portrait-landscape split strategy."""
        return False


class DefaultLayoutStrategy(LayoutStrategy):
    """Default layout strategy using grid layouts."""

    # CSS Grid layout definitions matching album.html template
    # Format: columns_fr, rows_fr, first_photo_row_span
    _GRID_LAYOUTS: ClassVar[dict[int, tuple[list[float], list[float], int]]] = {
        1: ([1.0], [1.0], 1),
        2: ([1.0, 1.0], [1.0], 1),
        3: ([1.0, 1.0], [1.0, 1.0], 2),  # First photo spans 2 rows
        4: ([1.0, 1.0], [1.0, 1.0], 1),
        5: ([2.0, 1.0, 1.0], [1.0, 1.0], 2),  # First photo spans 2 rows
        6: ([2.0, 1.0, 1.0], [1.0, 1.0, 1.0], 3),  # First photo spans 3 rows
    }

    @property
    def name(self) -> str:
        return "default"

    def is_applicable(self, _count: int) -> bool:
        return True  # Applicable for any count, though specialized ones take precedence

    def validate_combo(self, _combo: tuple[Photo, ...]) -> bool:
        return True  # No specific constraints on photo types

    def calculate_score(self, combo: tuple[Photo, ...], count: int) -> float:
        score = 0.0
        # For multi-row layouts (5, 6 photos), prefer portrait in first position
        if count in settings.photo.multi_row_layout_counts and combo:
            first_photo = combo[0]
            first_ratio = get_photo_ratio(first_photo.width or 0, first_photo.height or 0)
            if first_ratio == PhotoRatio.PORTRAIT:
                score += settings.photo.score_portrait_first_bonus
        return score

    def sort_combo(self, combo: tuple[Photo, ...]) -> list[Photo]:
        return list(combo)

    def calculate_photo_area_percent(self, photo_count: int, photo_index: int) -> float:
        """Calculate area percentage for a photo in the default grid layout."""
        if photo_count == 1:
            return settings.photo.photo_area_full_page

        if photo_count in self._GRID_LAYOUTS:
            columns_fr, rows_fr, first_row_span = self._GRID_LAYOUTS[photo_count]
            total_columns = sum(columns_fr)
            total_rows = sum(rows_fr)

            if photo_index == 0:
                column_span = columns_fr[0]
                row_span = first_row_span
            else:
                cells_per_row = len(columns_fr) - 1
                if cells_per_row == 0:
                    column_span = columns_fr[0] if len(columns_fr) > 0 else 1.0
                else:
                    col_index = ((photo_index - 1) % cells_per_row) + 1
                    column_span = columns_fr[col_index]
                row_span = 1

            area_percent = (
                (column_span / total_columns)
                * (row_span / total_rows)
                * settings.photo.photo_area_full_page
            )
            return round(area_percent, 1)

        return round(settings.photo.photo_area_full_page / photo_count, 1)


class ThreePortraitsStrategy(LayoutStrategy):
    """Strategy for 3 portraits side-by-side."""

    @property
    def name(self) -> str:
        return "three_portraits"

    @property
    def is_three_portraits(self) -> bool:
        return True

    def is_applicable(self, count: int) -> bool:
        return count == settings.photo.photo_count_for_special_layouts

    def validate_combo(self, combo: tuple[Photo, ...]) -> bool:
        return is_three_portraits(combo)

    def calculate_score(self, combo: tuple[Photo, ...], _count: int) -> float:
        score = settings.photo.score_three_portraits_bonus
        score += settings.photo.score_layout_bonus_three_portraits

        # Extra bonus if all 3 portraits have the same aspect ratio
        aspect_ratios = [
            ((p.width or 0) / (p.height or 1) if (p.height or 0) > 0 else 0) for p in combo
        ]
        rounded_ratios = {round(ar, 2) for ar in aspect_ratios}
        if len(rounded_ratios) == 1:
            score += settings.photo.score_uniform_aspect_ratio_bonus

        return score

    def sort_combo(self, combo: tuple[Photo, ...]) -> list[Photo]:
        return list(combo)

    def calculate_photo_area_percent(self, _photo_count: int, _photo_index: int) -> float:
        return round(settings.photo.photo_area_three_portraits, 1)


class PortraitLandscapeSplitStrategy(LayoutStrategy):
    """Strategy for 1 portrait and 2 landscapes."""

    @property
    def name(self) -> str:
        return "portrait_landscape_split"

    @property
    def is_portrait_landscape_split(self) -> bool:
        return True

    def is_applicable(self, count: int) -> bool:
        return count == settings.photo.photo_count_for_special_layouts

    def validate_combo(self, combo: tuple[Photo, ...]) -> bool:
        return is_one_portrait_two_landscapes(combo)

    def calculate_score(self, _combo: tuple[Photo, ...], _count: int) -> float:
        return settings.photo.score_portrait_landscape_split_bonus

    def sort_combo(self, combo: tuple[Photo, ...]) -> list[Photo]:
        # Sort: portrait first, then landscapes
        return sorted(
            combo,
            key=lambda p: (
                0 if get_photo_ratio(p.width or 0, p.height or 0) == PhotoRatio.PORTRAIT else 1
            ),
        )

    def calculate_photo_area_percent(self, _photo_count: int, photo_index: int) -> float:
        if photo_index == 0:
            return settings.photo.photo_area_portrait_left
        return settings.photo.photo_area_landscape_right
