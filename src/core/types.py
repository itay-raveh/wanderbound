"""Type aliases and Pydantic models for commonly used data structures."""

from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from src.data.models import FlagResult, MapResult, Photo, Step, TripData, WeatherResult


class PhotoPageData(TypedDict):
    photos: list[str]
    is_three_portraits: bool
    is_portrait_landscape_split: bool


class StepData(TypedDict):
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


class StepExternalData(TypedDict):
    elevation: float | None
    weather_data: "WeatherResult | None"
    flag_data: "FlagResult | None"
    map_data: "MapResult | None"
    cover_image_path: str | None


class AlbumPhotoData(TypedDict):
    steps_with_photos: dict[int, list["Photo"]]
    steps_cover_photos: dict[int, "Photo | None"]
    steps_photo_pages: dict[int, list[list["Photo"]]]


class AlbumGenerationConfig(TypedDict):
    trip_data: "TripData"
    output_dir: Path


class StepContext(TypedDict):
    step: "Step"
    step_index: int
    steps: list["Step"]
    trip_data: "TripData"


__all__ = [
    "AlbumGenerationConfig",
    "AlbumPhotoData",
    "PhotoPageData",
    "StepContext",
    "StepData",
    "StepExternalData",
]
