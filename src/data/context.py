from pathlib import Path

from pydantic import BaseModel, Field

from src.data.locations import LocationEntry, TravelSegment
from src.data.media import AssetPhoto, PhotoPageData


class StepTemplateContext(BaseModel):
    id: int
    name: str
    country: str
    country_code: str
    coords_lat: str
    coords_lon: str
    lat_val: float
    lon_val: float
    date_month: str
    date_day: str
    day_weather_icon_url: str | None
    night_weather_icon_url: str | None
    temp_str: str
    temp_night_str: str
    altitude_str: str
    day_num: int
    progress_percent: float
    day_counter_box_position: float
    day_counter_arrow_position: float
    cover_photo_path: Path | None
    cover_photo_id: str | None = None
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
    hidden_photos: list[AssetPhoto] = Field(default_factory=list)
    light_mode: bool


class TripTemplateContext(BaseModel):
    """Processed trip data for the title page template."""

    title: str
    date_range: str
    summary: str | None
    cover_photo_path: str | None
    title_dir: str
    summary_dir: str
    path_points: list[LocationEntry]
    path_segments: list[TravelSegment]


class TripOverviewTemplateCtx(BaseModel):
    countries: list[tuple[str, str]]  # (name, flag_url)
    total_km: str
    total_days: int
    step_count: int
    photo_count: int
