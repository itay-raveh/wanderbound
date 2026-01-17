from dataclasses import dataclass
from pathlib import Path

from src.data.layout import PageLayout
from src.data.segments import Segment


@dataclass
class StepTemplateCtx:
    id: int
    index: int
    name: str
    country: str
    coords_lat: str
    coords_lon: str
    lat_val: float
    lon_val: float
    date_month: str
    date_day: str
    day_weather_icon_url: str
    night_weather_icon_url: str
    temp_str: str
    temp_night_str: str
    altitude_str: str
    progress_percent: float
    day_counter_box_position: float
    day_counter_arrow_position: float
    cover_photo: Path
    country_flag_data_uri: str
    country_map_svg: str
    map_dot_x: float
    map_dot_y: float
    accent_color: str
    description: str
    desc_dir: str
    is_long_description: bool
    photo_pages: list[PageLayout]
    hidden_photos: list[Path]


@dataclass
class TripTemplateCtx:
    title: str
    title_dir: str
    dates: str
    subtitle: str | None
    subtitle_dir: str
    cover: str | None
    back_cover: str | None
    segments: list[Segment]


@dataclass
class OverviewTemplateCtx:
    countries: list[tuple[str, str]]  # (name, flag_url)
    total_km: str
    total_days: int
    step_count: int
    photo_count: int


@dataclass
class MapTemplateCtx:
    id: str  # DOM container ID
    segments: list[Segment]
    steps: list[StepTemplateCtx]
