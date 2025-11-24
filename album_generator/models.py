"""Pydantic models for trip data validation."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Location(BaseModel):
    """Location data for a step."""

    id: int
    name: str | None = None
    detail: str | None = None
    full_detail: str | None = None
    country_code: str
    lat: float
    lon: float
    venue: str | None = None
    uuid: str | None = None


class Step(BaseModel):
    """Step data from trip."""

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

    @property
    def city(self) -> str:
        """Get city name."""
        return self.display_name or self.name or "Unknown"

    @property
    def country(self) -> str:
        """Get country name."""
        return self.location.detail or self.location.full_detail or ""

    @property
    def country_code(self) -> str:
        """Get country code."""
        return self.location.country_code

    def get_name_for_photos_export(self) -> str:
        """Get step name for photos export file (similar to reference implementation)."""
        return f"{self.city} ({self.country})"


class TripData(BaseModel):
    """Trip metadata."""

    id: int | None = None
    name: str | None = None
    start_date: float | None = None
    end_date: float | None = None
    timezone_id: str = "UTC"
    all_steps: list[Step] = Field(default_factory=list)
    total_km: float | None = None
    step_count: int | None = None


class WeatherData(BaseModel):
    """Structured weather data from API."""

    day_temp: float | None = None
    night_temp: float | None = None
    day_feels_like: float | None = None
    night_feels_like: float | None = None
    day_icon: str | None = None
    night_icon: str | None = None


class Photo(BaseModel):
    """Photo metadata for a step."""

    id: str  # Filename
    index: int  # Order index (1-based)
    path: Path  # Full path to photo file
    width: int | None = None
    height: int | None = None
    aspect_ratio: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert photo to dictionary for JSON serialization."""
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
        """Create Photo from dictionary."""
        return cls(
            id=data["id"],
            index=data["index"],
            path=Path(data["path"]),
            width=data.get("width"),
            height=data.get("height"),
            aspect_ratio=data.get("aspect_ratio"),
        )
