from datetime import datetime
from pathlib import Path
from typing import Annotated, Self
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    Field,
    HttpUrl,
)

from app.models.geo import CountryCode, Lat, Lon

NullableStr = Annotated[str, BeforeValidator(lambda v: v or "")]


class Point(BaseModel):
    lat: Lat
    lon: Lon
    time: float

    def __lt__(self, other: Point) -> bool:
        return self.time < other.time


class PSLocations(BaseModel):
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

    def __lt__(self, other: PSStep) -> bool:
        return self.datetime < other.datetime

    @property
    def folder_name(self) -> str:
        return f"{self.slug}_{self.id}"

    @property
    def datetime(self) -> AwareDatetime:
        return datetime.fromtimestamp(self.timestamp, ZoneInfo(self.timezone_id))


class PSTrip(BaseModel):
    id: int
    slug: str
    title: str = Field(alias="name")
    subtitle: NullableStr = Field(alias="summary")
    cover_photo_path: HttpUrl
    step_count: int
    all_steps: list[PSStep]

    @classmethod
    def from_trip_dir(cls, trip_dir: Path) -> Self:
        obj = cls.model_validate_json((trip_dir / "trip.json").read_bytes())
        obj.all_steps.sort(key=lambda s: s.timestamp)
        return obj
