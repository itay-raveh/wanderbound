"""Pydantic models for trip data validation."""
from pydantic import BaseModel, Field
from typing import Optional, List


class Location(BaseModel):
    """Location data for a step."""
    id: int
    name: Optional[str] = None
    detail: Optional[str] = None
    full_detail: Optional[str] = None
    country_code: str
    lat: float
    lon: float
    venue: Optional[str] = None
    uuid: Optional[str] = None


class Step(BaseModel):
    """Step data from trip."""
    id: int
    trip_id: Optional[int] = None
    name: Optional[str] = None
    display_name: str
    slug: Optional[str] = None
    display_slug: Optional[str] = None
    description: Optional[str] = None
    location: Location
    location_id: Optional[int] = None
    start_time: float
    end_time: Optional[float] = None
    timezone_id: str
    weather_condition: Optional[str] = None
    weather_temperature: Optional[float] = None
    main_media_item_path: Optional[str] = None
    comment_count: Optional[int] = None
    views: Optional[int] = None
    is_deleted: Optional[bool] = None
    type: Optional[str | int] = None  # Can be string or int in the data
    supertype: Optional[str] = None
    creation_time: Optional[float] = None
    fb_publish_status: Optional[str] = None
    open_graph_id: Optional[str] = None
    uuid: Optional[str] = None
    
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


class TripData(BaseModel):
    """Trip metadata."""
    id: Optional[int] = None
    name: Optional[str] = None
    start_date: Optional[float] = None
    end_date: Optional[float] = None
    timezone_id: str = "UTC"
    all_steps: List[Step] = Field(default_factory=list)
    total_km: Optional[float] = None
    step_count: Optional[int] = None
