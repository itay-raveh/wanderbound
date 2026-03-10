import math
from datetime import datetime
from pathlib import Path
from typing import Annotated, Self
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    HttpUrl,
)

from app.core.config import settings
from app.logic.country_colors import CountryCode
from app.logic.spatial.points import Lat, Lon, Point

NullableStr = Annotated[str, BeforeValidator(lambda v: v or "")]


class Locations(BaseModel):
    locations: list[Point]

    @classmethod
    def from_trip_dir(cls, trip_dir: Path) -> Self:
        obj = cls.model_validate_json((trip_dir / "locations.json").read_bytes())
        obj.locations.sort()
        return obj


class Location(BaseModel):
    name: NullableStr
    detail: NullableStr
    country_code: CountryCode
    lat: Lat
    lon: Lon


class PSStep(BaseModel):
    id: int
    name: str = Field(validation_alias="display_name")
    slug: str = Field(validation_alias="display_slug")
    description: NullableStr
    timestamp: float = Field(validation_alias="start_time")
    timezone_id: str
    location: Location
    weather_condition: str
    weather_temperature: float

    def __lt__(self, other: PSStep) -> bool:
        return self.datetime < other.datetime

    @property
    def folder_name(self) -> str:
        return f"{self.slug}_{self.id}"

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, ZoneInfo(self.timezone_id))

    @property
    def is_long_description(self) -> bool:
        return _calculate_visual_length(self.description) > settings.long_description_threshold


class TripCoverPhoto(BaseModel):
    path: HttpUrl


class Trip(BaseModel):
    id: int
    slug: str
    title: str = Field(alias="name")
    subtitle: NullableStr = Field(alias="summary")
    cover_photo: TripCoverPhoto
    step_count: int
    all_steps: list[PSStep]

    @property
    def name(self) -> str:
        return f"{self.slug}_{self.id}"

    @classmethod
    def from_trip_dir(cls, trip_dir: Path) -> Self:
        obj = cls.model_validate_json((trip_dir / "trip.json").read_bytes())
        obj.all_steps.sort(key=lambda s: s.timestamp)
        return obj


_WIDTH = 80


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
