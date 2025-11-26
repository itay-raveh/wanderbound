"""Type aliases and TypedDict definitions for commonly used data structures."""

from typing import TypedDict


class PhotoPageData(TypedDict):
    """Represents a single photo page with its layout flags."""

    photos: list[str]
    is_three_portraits: bool
    is_portrait_landscape_split: bool


class StepData(TypedDict, total=False):
    """Dictionary structure for step data passed to templates."""

    city: str
    country: str
    country_code: str
    coords_lat: str
    coords_lon: str
    date_month: str
    date_day: str
    weather: str
    day_weather_icon_url: str | None
    night_weather_icon_url: str | None
    temp_str: str
    temp_night_str: str
    altitude_str: str
    day_num: int
    progress_percent: float
    day_counter_box_position: float
    day_counter_arrow_position: float
    cover_image_path: str | None
    country_flag_data_uri: str | None
    country_map_data_uri: str | None
    country_map_svg: str | None
    map_dot_x: float | None
    map_dot_y: float | None
    accent_color: str | None
    description: str | None
    description_full: str
    desc_dir: str
    desc_align: str
    use_two_columns: bool
    use_three_columns: bool
    photo_pages: list[PhotoPageData]
    light_mode: bool


__all__ = [
    "PhotoPageData",
    "StepData",
]
