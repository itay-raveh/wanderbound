"""Pydantic models for trip data validation."""

from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    Field,
)

from src.data.locations import Location, LocationEntry, TravelSegment


class Step(BaseModel):
    id: int
    trip_id: int
    name: str | None = None
    display_name: str
    slug: str
    display_slug: str
    description: str | None = None
    location: Location
    location_id: int
    start_time: float = Field(..., gt=0)
    end_time: float | None = None
    timezone_id: str
    weather_condition: str | None = None
    weather_temperature: float | None = None
    main_media_item_path: str | None = None
    comment_count: int = Field(ge=0)
    views: int = Field(ge=0)
    is_deleted: bool
    type: str | int
    supertype: str
    creation_time: float
    fb_publish_status: str | None = None
    open_graph_id: str | None = None
    uuid: str

    @property
    def city(self) -> str:
        return self.display_name or self.name or "Unknown"

    @property
    def country(self) -> str:
        return self.location.detail or self.location.full_detail or ""

    @property
    def country_code(self) -> str:
        return self.location.country_code

    def get_name_for_photos_export(self) -> str:
        return f"{self.city} ({self.country})"


class CoverPhoto(BaseModel):
    uuid: str | None = None
    url: str | None = Field(default=None, alias="path")


class TripData(BaseModel):
    id: int
    name: str
    start_date: float
    end_date: float
    timezone_id: str
    all_steps: list[Step] = Field(default_factory=list)
    total_km: float = Field(ge=0)
    step_count: int = Field(ge=0)
    title: str | None = None
    summary: str | None = None
    cover_photo: CoverPhoto | None = None


class TripDisplayData(BaseModel):
    """Processed trip data for the title page template."""

    display_title: str
    display_date_range: str | None
    summary: str | None
    cover_photo_path: str | None
    title_dir: str
    summary_dir: str
    trip: TripData
    path_points: list[LocationEntry] | None = None
    path_segments: list[TravelSegment] | None = None


class WeatherData(BaseModel):
    day_temp: float | None = Field(None, ge=-100, le=100)
    night_temp: float | None = Field(None, ge=-100, le=100)
    day_feels_like: float | None = Field(None, ge=-100, le=100)
    night_feels_like: float | None = Field(None, ge=-100, le=100)
    day_icon: str | None = None
    night_icon: str | None = None


class WeatherResult(BaseModel):
    step_index: int
    data: WeatherData | None = None


class FlagResult(BaseModel):
    step_index: int
    flag_url: str | None = None
    accent_color: str | None = None


class MapResult(BaseModel):
    step_index: int
    svg_content: str | None = None
    dot_position: tuple[float, float] | None = None


class TripSummary(BaseModel):
    countries: list[tuple[str, str | None]]  # (name, flag_url)
    total_km: int
    total_days: int
    step_count: int
    photo_count: int
    start_date: str | None = None
    end_date: str | None = None


class Photo(BaseModel):
    id: str
    index: int = Field(..., gt=0)
    path: Path
    width: int | None = Field(None, gt=0)
    height: int | None = Field(None, gt=0)
    aspect_ratio: float | None = Field(None, gt=0)


PhotoLayout = Literal["three-portraits", "portrait-landscape-split"]


class PhotoPageData(BaseModel):
    photos: list[str]
    layout_class: PhotoLayout | None = None
    grid_style: str | None = None


class StepExternalData(BaseModel):
    elevation: float | None
    weather_data: WeatherResult | None
    flag_data: FlagResult | None
    map_data: MapResult | None
    cover_image_path: str | None


class StepData(BaseModel):
    city: str
    country: str
    country_code: str
    coords_lat: str
    coords_lon: str
    lat_val: float
    lon_val: float
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
    description: str
    desc_dir: str
    desc_align: str
    use_two_columns: bool
    use_three_columns: bool
    photo_pages: list[PhotoPageData]
    light_mode: bool


class AlbumPhotoData(BaseModel):
    steps_with_photos: dict[int, list[Photo]]
    steps_cover_photos: dict[int, Photo | None]
    steps_photo_pages: dict[int, list[list[Photo]]]


class AlbumGenerationConfig(BaseModel):
    trip_data: TripData
    trip_display_data: TripDisplayData | None = None
    output_dir: Path


class StepContext(BaseModel):
    step: Step
    step_index: int
    steps: list[Step]
    trip_data: TripData
