from datetime import datetime
from functools import cached_property
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import AliasChoices, BaseModel, BeforeValidator, Field, field_validator

from psagen.core.settings import settings
from psagen.core.text import calculate_visual_length

NullableStr = Annotated[str, BeforeValidator(lambda v: v or "")]  # pyright: ignore[reportAny]


class Location(BaseModel, extra="ignore"):
    city: NullableStr = Field(alias="name")
    country: NullableStr = Field(validation_alias=AliasChoices("country", "detail"))
    country_code: str = Field(pattern=r"^[A-Za-z]{2}$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

    @field_validator("country_code", mode="before")
    @classmethod
    def country_code_validator(cls, v: str) -> str:
        return "un" if v == "00" else v


class Step(BaseModel):
    id: int
    name: str = Field(alias="display_name")
    slug: str = Field(alias="display_slug")
    description: NullableStr
    start_time: float
    timezone_id: str
    location: Location
    weather_condition: str
    weather_temperature: float

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


class TripCoverPhoto(BaseModel):
    path: str


class TripHeader(BaseModel):
    id: int
    slug: str
    title: str = Field(alias="name")
    subtitle: NullableStr = Field(alias="summary")
    cover_photo: TripCoverPhoto
    start_time: float = Field(alias="start_date")
    end_time: float = Field(alias="end_date")
    timezone_id: str
    step_count: int

    @property
    def name(self) -> str:
        return f"{self.slug}_{self.id}"

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_id)

    @property
    def start_date(self) -> datetime:
        return datetime.fromtimestamp(self.start_time, tz=self.timezone)

    @property
    def end_date(self) -> datetime:
        return datetime.fromtimestamp(self.end_time, tz=self.timezone)


class Trip(TripHeader):
    all_steps: list[Step]
