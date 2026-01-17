from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, BeforeValidator, Field

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
    def folder_name(self) -> str:
        return f"{self.slug}_{self.id}"

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_id)

    @cached_property
    def date(self) -> datetime:
        return datetime.fromtimestamp(self.start_time, tz=self.timezone)


class TripCover(BaseModel):
    uuid: str | None = None
    url: str | None = Field(None, alias="path")


class Trip(BaseModel):
    title: str = Field(alias="name")
    subtitle: _Str = Field(alias="summary")
    cover_photo: TripCover
    start_time: float = Field(alias="start_date")
    end_time: float = Field(alias="end_date")
    timezone_id: str
    all_steps: list[Step]

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
    day_temp: float
    night_temp: float
    day_feels_like: float
    night_feels_like: float
    day_icon: str
    night_icon: str


@dataclass
class Flag:
    flag_url: str
    accent_color: str


@dataclass
class Map:
    svg_content: str
    dot_position: tuple[float, float]


class EnrichedStep(Step):
    altitude: float
    weather: Weather
    flag: Flag
    map: Map
