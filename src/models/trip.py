from datetime import datetime
from functools import cached_property
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, BeforeValidator, Field

from src.core.settings import settings
from src.core.text import calculate_visual_length

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

    @property
    def is_long_description(self) -> bool:
        return calculate_visual_length(self.description) > settings.long_description_threshold

    @property
    def is_extra_long_description(self) -> bool:
        return calculate_visual_length(self.description) > settings.extra_long_description_threshold


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


class Weather(BaseModel):
    day_temp: float
    night_temp: float
    day_feels_like: float
    night_feels_like: float
    day_icon: str
    night_icon: str


class Flag(BaseModel):
    flag_url: str
    accent_color: str


class Map(BaseModel):
    svg_content: str
    dot_position: tuple[float, float]


class EnrichedStep(Step):
    altitude: float
    weather: Weather
    flag: Flag
    map: Map
