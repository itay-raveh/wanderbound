"""Type aliases and TypedDict definitions for commonly used data structures."""

from typing import Any, TypedDict

from .models import Photo, Step


class StepDataDict(TypedDict, total=False):
    """Dictionary structure for step data passed to templates."""

    step: Step
    cover_photo: Photo | None
    cover_image_path: str | None
    date_data: dict[str, str]
    coords_data: dict[str, str]
    day_num: int
    progress_percent: float
    arrow_bar_position: float
    box_center_position: float
    elevation: float | None
    day_temp_display: str
    night_temp_display: str
    day_weather_icon_url: str | None
    night_weather_icon_url: str | None
    country_flag_data_uri: str | None
    accent_color: str | None
    country_map_data_uri: str | None
    country_map_svg: str | None
    map_dot_x: float | None
    map_dot_y: float | None
    desc_col1: str
    desc_col2: str
    desc_col3: str
    is_hebrew: bool
    use_two_columns: bool
    use_three_columns: bool
    photo_pages: list[list[Photo]]
    photo_page_layouts: list[bool]
    photo_page_portrait_split_layouts: list[bool]


class PhotoConfigDict(TypedDict, total=False):
    """Dictionary structure for photo configuration loaded from files."""

    cover_photo_index: int | None
    photo_pages: list[list[int]]
    photos: dict[str, dict[str, Any]]
    is_three_portraits: list[bool]
    is_portrait_landscape_split: list[bool]


__all__ = ["StepDataDict", "PhotoConfigDict"]
