from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    FiniteFloat,
    field_validator,
    model_validator,
)
from sqlalchemy import DateTime, String
from sqlmodel import Column, Field, SQLModel

from app.core.db import PydanticJSON, all_optional
from app.models.album_media import AlbumMedia
from app.models.polarsteps import CountryCode, HexColor
from app.models.segment import Segment
from app.models.step import StepRead

type DateRange = tuple[date, date]

HeaderKey = Literal["cover-front", "cover-back", "overview", "full-map"]
MediaResolutionWarningPreset = Literal["off", "relaxed", "print"]

PAGE_ASPECT_RATIO = {"minimum": 1.25, "maximum": 1.8}

DEFAULT_FONT = "Assistant"
DEFAULT_BODY_FONT = "Frank Ruhl Libre"
DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET: MediaResolutionWarningPreset = "relaxed"
DEMO_MEDIA_RESOLUTION_WARNING_PRESET: MediaResolutionWarningPreset = "off"


class AlbumChapter(SQLModel):
    id: str = Field(max_length=80)
    title: str = Field(max_length=255)
    subtitle: str = Field(max_length=255)
    step_ids: list[int] = Field(default_factory=list)
    front_cover_photo: str = Field(max_length=255)
    back_cover_photo: str = Field(max_length=255)
    front_cover_darkness: float = Field(default=0.45, ge=0.0, le=1.0)
    spine_width_mm: float = Field(default=0, ge=0, le=100)


class AlbumBase(SQLModel):
    """User-editable settings."""

    # JSON Schema has no standard constraint for a ratio of two properties.
    model_config = ConfigDict(
        json_schema_extra={"x-page-aspect-ratio": PAGE_ASPECT_RATIO}
    )

    colors: dict[CountryCode, HexColor] = Field(
        sa_column=Column(PydanticJSON(dict[CountryCode, HexColor]), nullable=False)
    )
    background_color: HexColor | None = Field(
        default=None, sa_column=Column(String(7), nullable=True)
    )
    hidden_steps: list[int] = Field(
        sa_column=Column(PydanticJSON(list[int]), nullable=False),
        default_factory=list,
    )
    hidden_headers: list[HeaderKey] = Field(
        sa_column=Column(PydanticJSON(list[HeaderKey]), nullable=False),
        default_factory=list,
    )
    maps_ranges: list[DateRange] = Field(
        sa_column=Column(PydanticJSON(list[DateRange]), nullable=False),
        default_factory=list,
    )
    chapters: list[AlbumChapter] = Field(
        sa_column=Column(PydanticJSON(list[AlbumChapter]), nullable=False),
        default_factory=list,
    )
    font: str = Field(
        default=DEFAULT_FONT,
        sa_column=Column(String(100), nullable=False, default=DEFAULT_FONT),
    )
    body_font: str = Field(
        default=DEFAULT_BODY_FONT,
        sa_column=Column(String(100), nullable=False, default=DEFAULT_BODY_FONT),
    )
    page_width_mm: FiniteFloat = Field(default=297, ge=250, le=420)
    page_height_mm: FiniteFloat = Field(default=210, ge=180, le=297)
    safe_margin_mm: int = Field(default=5, ge=0, le=15)
    show_page_numbers: bool = Field(default=False)
    interior_bleed_mm: float = Field(default=0, ge=0, le=20)
    cover_bleed_mm: float = Field(default=0, ge=0, le=20)
    media_resolution_warning_preset: MediaResolutionWarningPreset = Field(
        default=DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
        sa_column=Column(
            String(20),
            nullable=False,
            default=DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
        ),
    )

    @model_validator(mode="after")
    def valid_page_dimensions(self) -> AlbumBase:
        width, height = self.page_width_mm, self.page_height_mm
        if width is None or height is None:
            raise ValueError("Page dimensions must not be null")
        minimum, maximum = PAGE_ASPECT_RATIO["minimum"], PAGE_ASPECT_RATIO["maximum"]
        if not minimum <= width / height <= maximum:
            raise ValueError(
                f"Page width / height must be between {minimum} and {maximum}"
            )
        return self


@all_optional
class AlbumUpdate(AlbumBase):
    @model_validator(mode="after")
    def dimensions_updated_together(self) -> AlbumUpdate:
        supplied = {"page_width_mm", "page_height_mm"} & self.model_fields_set
        if len(supplied) == 1:
            raise ValueError("Supply both page dimensions together")
        return self

    @field_validator("colors")
    @classmethod
    def colors_not_null(cls, value: dict[str, str] | None) -> dict[str, str]:
        if value is None:
            raise ValueError("Colors must be an object")
        return value


class AlbumMeta(AlbumBase):
    """GET/PATCH response - everything except media."""

    uid: int = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    id: str = Field(primary_key=True)


class Album(AlbumMeta, table=True):
    """Full DB row."""

    last_active_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AlbumWithMedia(AlbumMeta):
    media: list[AlbumMedia] = Field(default_factory=list)


class PrintBundle(BaseModel):
    """Everything needed for PDF rendering in one response."""

    album: AlbumWithMedia
    steps: list[StepRead]
    segments: list[Segment]
    total_distance_km: float


AlbumWithMedia.model_rebuild()
