"""Pydantic models for trip data validation."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Location(BaseModel):
    id: int
    name: str | None = None
    detail: str | None = None
    full_detail: str | None = None
    country_code: str
    lat: float
    lon: float
    venue: str | None = None
    uuid: str | None = None

    @field_validator("lat")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError(f"Latitude must be between -90 and 90, got {v}")
        return v

    @field_validator("lon")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError(f"Longitude must be between -180 and 180, got {v}")
        return v


class Step(BaseModel):
    id: int
    trip_id: int | None = None
    name: str | None = None
    display_name: str
    slug: str | None = None
    display_slug: str | None = None
    description: str | None = None
    location: Location
    location_id: int | None = None
    start_time: float
    end_time: float | None = None
    timezone_id: str
    weather_condition: str | None = None
    weather_temperature: float | None = None
    main_media_item_path: str | None = None
    comment_count: int | None = None
    views: int | None = None
    is_deleted: bool | None = None
    type: str | int | None = None  # Can be string or int in the data
    supertype: str | None = None
    creation_time: float | None = None
    fb_publish_status: str | None = None
    open_graph_id: str | None = None
    uuid: str | None = None

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"start_time must be a positive Unix timestamp, got {v}")
        return v

    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v: float | None, info: Any) -> float | None:
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
    id: int | None = None
    name: str | None = None
    start_date: float | None = None
    end_date: float | None = None
    timezone_id: str = "UTC"
    all_steps: list[Step] = Field(default_factory=list)
    total_km: float | None = None
    step_count: int | None = None


class WeatherData(BaseModel):
    day_temp: float | None = None
    night_temp: float | None = None
    day_feels_like: float | None = None
    night_feels_like: float | None = None
    day_icon: str | None = None
    night_icon: str | None = None

    @field_validator("day_temp", "night_temp", "day_feels_like", "night_feels_like")
    @classmethod
    def validate_temperature(cls, v: float | None) -> float | None:
        # Reasonable range: -100°C to 100°C (covers all Earth temperatures)
        if v is not None and not -100 <= v <= 100:
            raise ValueError(f"Temperature must be between -100 and 100°C, got {v}")
        return v


class Photo(BaseModel):
    id: str  # Filename
    index: int  # Order index (1-based)
    path: Path  # Full path to photo file
    width: int | None = None
    height: int | None = None
    aspect_ratio: float | None = None

    @field_validator("index")
    @classmethod
    def validate_index(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"Photo index must be positive, got {v}")
        return v

    @field_validator("width", "height")
    @classmethod
    def validate_dimensions(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError(f"Photo dimensions must be positive, got {v}")
        return v

    @field_validator("aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError(f"Aspect ratio must be positive, got {v}")
        return v

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "index": self.index,
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "aspect_ratio": self.aspect_ratio,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Photo":
        return cls(
            id=data["id"],
            index=data["index"],
            path=Path(data["path"]),
            width=data.get("width"),
            height=data.get("height"),
            aspect_ratio=data.get("aspect_ratio"),
        )
