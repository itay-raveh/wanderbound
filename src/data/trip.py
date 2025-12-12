from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, BeforeValidator, Field

from src.data.context import TripTemplateContext
from src.data.locations import Location
from src.data.media import CoverPhoto


class Step(BaseModel):
    id: int
    name: str = Field(alias="display_name")
    slug: str = Field(alias="display_slug")
    description: Annotated[str, BeforeValidator(lambda v: v or "")]
    start_time: float
    timezone_id: str
    location: Location

    @property
    def dir_name(self) -> str:
        return f"{self.slug}_{self.id}"

    @cached_property
    def date(self) -> datetime:
        return datetime.fromtimestamp(self.start_time, tz=ZoneInfo(self.timezone_id))


class Trip(BaseModel):
    name: str
    start_date: float
    end_date: float
    timezone_id: str
    all_steps: list[Step]
    summary: str | None
    cover_photo: CoverPhoto | None


class WeatherData(BaseModel):
    day_temp: float | None = None
    night_temp: float | None = None
    day_feels_like: float | None = None
    night_feels_like: float | None = None
    day_icon: str | None = None
    night_icon: str | None = None


class FlagData(BaseModel):
    flag_url: str | None = None
    accent_color: str | None = None


class MapData(BaseModel):
    svg_content: str
    dot_position: tuple[float, float]


class StepExternalData(BaseModel):
    elevation: float | None
    weather_data: WeatherData
    flag_data: FlagData | None
    map_data: MapData | None
    cover_photo_path: Path | None
    cover_photo_id: str | None


class AlbumGenerationConfig(BaseModel):
    trip: Trip
    trip_template_ctx: TripTemplateContext | None
    output_dir: Path
    trip_dir: Path
    editor_mode: bool = False


class StepContext(BaseModel):
    step: Step
    step_index: int
    steps: list[Step]
    trip: Trip
