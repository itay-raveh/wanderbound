from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, BeforeValidator, Field

from src.data.context import TripTemplateContext
from src.data.media import CoverPhoto

_Str = Annotated[str, BeforeValidator(lambda v: v or "")]  # pyright: ignore[reportAny]


class Location(BaseModel):
    country: str = Field(alias="detail")
    country_code: str = Field(pattern=r"^[A-Za-z]{2}$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Step(BaseModel):
    id: int
    name: str = Field(alias="display_name")
    slug: str = Field(alias="display_slug")
    description: _Str
    start_time: float
    timezone_id: str
    location: Location

    @property
    def dir_name(self) -> str:
        return f"{self.slug}_{self.id}"

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_id)

    @cached_property
    def date(self) -> datetime:
        return datetime.fromtimestamp(self.start_time, tz=self.timezone)


class Trip(BaseModel):
    name: str
    start_time: float = Field(validation_alias="start_date")
    end_time: float = Field(validation_alias="end_date")
    timezone_id: str
    all_steps: Sequence[Step]
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
class Weather:
    day_temp: float | None = None
    night_temp: float | None = None
    day_feels_like: float | None = None
    night_feels_like: float | None = None
    day_icon: str | None = None
    night_icon: str | None = None


@dataclass
class Flag:
    flag_url: str
    accent_color: str


@dataclass
class Map:
    svg_content: str
    dot_position: tuple[float, float]


@dataclass
class AlbumGenerationConfig:
    trip: Trip
    trip_template_ctx: TripTemplateContext
    output_dir: Path
    trip_dir: Path
    editor_mode: bool = False


class EnrichedStep(Step):
    altitude: float
    weather: Weather
    flag: Flag
    map: Map


@dataclass
class StepContext:
    step: EnrichedStep
    cover_photo: Path
    step_index: int
    steps: Sequence[EnrichedStep]
