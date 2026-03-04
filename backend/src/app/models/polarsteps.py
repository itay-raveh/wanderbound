import math
from datetime import UTC, datetime
from typing import Annotated, Self
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    Field,
    HttpUrl,
)

from app.core.settings import settings
from app.logic.data.country_colors import CountryCode

NullableStr = Annotated[str, BeforeValidator(lambda v: v or "")]  # pyright: ignore[reportAny]


class PSPoint(BaseModel):
    lat: float
    lon: float
    time: float

    @property
    def datetime(self) -> AwareDatetime:
        # TODO: check the timezone: Is it by the trip? UTC?
        return datetime.fromtimestamp(self.time)  # , UTC)

    def __lt__(self, other: Self) -> bool:
        return self.time < other.time


class PSLocations(BaseModel):
    locations: list[PSPoint]


class PSLocation(BaseModel):
    name: NullableStr
    detail: NullableStr
    country_code: CountryCode
    lat: float
    lon: float


class PSStep(BaseModel):
    id: int
    name: str = Field(validation_alias="display_name")
    slug: str = Field(validation_alias="display_slug")
    description: NullableStr
    timestamp: float = Field(validation_alias="start_time")
    timezone_id: str
    location: PSLocation
    weather_condition: str
    weather_temperature: float

    def __lt__(self, other: PSStep) -> bool:
        return self.datetime < other.datetime

    @property
    def folder_name(self) -> str:
        return f"{self.slug}_{self.id}"

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_id)

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=self.timezone)

    @property
    def is_long_description(self) -> bool:
        return _calculate_visual_length(self.description) > settings.long_description_threshold

    @property
    def is_extra_long_description(self) -> bool:
        return (
            _calculate_visual_length(self.description) > settings.extra_long_description_threshold
        )


class TripCoverPhoto(BaseModel):
    path: HttpUrl


class PSTrip(BaseModel):
    id: int
    slug: str
    title: str = Field(alias="name")
    subtitle: NullableStr = Field(alias="summary")
    cover_photo: TripCoverPhoto
    timezone_id: str
    step_count: int
    all_steps: list[PSStep]

    @property
    def name(self) -> str:
        return f"{self.slug}_{self.id}"

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_id)


def _calculate_visual_length(text: str) -> int:
    """Calculate visual length by simulating line wrapping.

    Returns estimated character consumption (lines * _WIDTH).
    """
    if not text:
        return 0

    lines = 0
    # Use split('\n') to preserve empty lines from consecutive/trailing newlines
    for para in text.split("\n"):
        if not para:
            lines += 1
        else:
            lines += math.ceil(len(para) / _WIDTH)

    return lines * _WIDTH


_WIDTH = 80
