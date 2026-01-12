from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, BeforeValidator, Field

from src.data.context import TripTemplateContext
from src.data.locations import Location
from src.data.media import CoverPhoto

_Str = Annotated[str, BeforeValidator(lambda v: v or "")]


class Step(BaseModel):
    id: int
    name: str = Field(validation_alias="display_name")
    slug: str = Field(validation_alias="display_slug")
    description: _Str
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
    start_time: float = Field(validation_alias="start_date")
    end_time: float = Field(validation_alias="end_date")
    timezone_id: str
    all_steps: list[Step]
    summary: _Str
    cover_photo: CoverPhoto

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_id)

    @property
    def start_date(self) -> datetime:
        return datetime.fromtimestamp(self.start_time, tz=self.timezone)

    @property
    def end_date(self) -> datetime:
        return datetime.fromtimestamp(self.end_time, tz=self.timezone)


@dataclass
class WeatherData:
    day_temp: float | None = None
    night_temp: float | None = None
    day_feels_like: float | None = None
    night_feels_like: float | None = None
    day_icon: str | None = None
    night_icon: str | None = None


@dataclass
class FlagData:
    flag_url: str
    accent_color: str


@dataclass
class MapData:
    svg_content: str
    dot_position: tuple[float, float]


@dataclass
class StepExternalData:
    elevation: float
    weather_data: WeatherData
    flag_data: FlagData
    map_data: MapData
    cover_photo: Path | None


@dataclass
class AlbumGenerationConfig:
    trip: Trip
    trip_template_ctx: TripTemplateContext | None
    output_dir: Path
    trip_dir: Path
    editor_mode: bool = False


@dataclass
class StepContext:
    step: Step
    step_index: int
    steps: list[Step]
    trip: Trip
