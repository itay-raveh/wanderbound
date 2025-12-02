"""Pydantic models for trip data validation."""

from pathlib import Path

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class Location(BaseModel):
    id: int
    name: str
    detail: str | None = None
    full_detail: str | None = None
    country_code: str = Field(..., min_length=2, max_length=2, pattern=r"^[A-Za-z0-9]{2}$")
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    venue: str | None = None
    uuid: str


class Step(BaseModel):
    id: int
    trip_id: int
    name: str | None = None
    display_name: str
    slug: str
    display_slug: str
    description: str | None = None
    location: Location
    location_id: int
    start_time: float = Field(..., gt=0)
    end_time: float | None = None
    timezone_id: str
    weather_condition: str | None = None
    weather_temperature: float | None = None
    main_media_item_path: str | None = None
    comment_count: int = Field(ge=0)
    views: int = Field(ge=0)
    is_deleted: bool
    type: str | int
    supertype: str
    creation_time: float
    fb_publish_status: str | None = None
    open_graph_id: str | None = None
    uuid: str

    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v: float | None, info: ValidationInfo) -> float | None:
        if v is not None:
            start_time = info.data.get("start_time")
            if start_time and v < start_time:
                raise ValueError(f"end_time ({v}) must be >= start_time ({start_time})")
        return v

    @property
    def city(self) -> str:
        return self.display_name or self.name or "Unknown"

    @property
    def country(self) -> str:
        return self.location.detail or self.location.full_detail or ""

    @property
    def country_code(self) -> str:
        return self.location.country_code

    def get_name_for_photos_export(self) -> str:
        return f"{self.city} ({self.country})"


class TripData(BaseModel):
    id: int
    name: str
    start_date: float
    end_date: float
    timezone_id: str = "UTC"
    all_steps: list[Step] = Field(default_factory=list)
    total_km: float = Field(ge=0)
    step_count: int = Field(ge=0)


class WeatherData(BaseModel):
    day_temp: float | None = Field(default=None, ge=-100, le=100)
    night_temp: float | None = Field(default=None, ge=-100, le=100)
    day_feels_like: float | None = Field(default=None, ge=-100, le=100)
    night_feels_like: float | None = Field(default=None, ge=-100, le=100)
    day_icon: str | None = None
    night_icon: str | None = None


class WeatherResult(BaseModel):
    step_index: int
    data: WeatherData | None = None


class FlagResult(BaseModel):
    step_index: int
    flag_url: str | None = None
    accent_color: str | None = None


class MapResult(BaseModel):
    step_index: int
    svg_content: str | None = None
    dot_position: tuple[float, float] | None = None


class Photo(BaseModel):
    id: str
    index: int = Field(..., gt=0)
    path: Path
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    aspect_ratio: float | None = Field(default=None, gt=0)
