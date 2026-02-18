from pathlib import Path

from pydantic import BaseModel

from psagen.logic.segments import Segment
from psagen.models.layout import PageLayout
from psagen.models.trip import Location


class StepTemplateCtx(BaseModel):
    id: int
    index: int
    name: str
    country: str
    lat_str: str
    lon_str: str
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
    extra_description: str | None
    is_long_description: bool
    photo_pages: list[PageLayout]
    hidden_photos: list[Path]


class TripTemplateCtx(BaseModel):
    title: str
    dates: str
    subtitle: str
    cover: str | None
    back_cover: str | None
    segments: list[Segment]


class FurthestPointCtx(BaseModel):
    home: Location
    furthest: Location
    distance_km: str


class OverviewTemplateCtx(BaseModel):
    countries: list[tuple[str, str]]  # (name, flag_url)
    total_km: str
    total_days: str
    step_count: str
    photo_count: str
    furthest_point: FurthestPointCtx | None = None


class MapTemplateCtx(BaseModel):
    id: str  # DOM container ID
    segments: list[Segment]
    steps: list[StepTemplateCtx]
