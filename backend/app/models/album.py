from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import String
from sqlmodel import Column, Field, SQLModel

from app.core.db import PydanticJSON, all_optional
from app.logic.layout.media import Media, MediaName
from app.models.google_photos import GoogleMediaId
from app.models.polarsteps import CountryCode, HexColor
from app.models.segment import Segment
from app.models.step import Step

type DateRange = tuple[date, date]

HeaderKey = Literal["cover-front", "cover-back", "overview", "full-map"]
MediaResolutionWarningPreset = Literal["off", "relaxed", "print"]

DEFAULT_FONT = "Assistant"
DEFAULT_BODY_FONT = "Frank Ruhl Libre"
DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET: MediaResolutionWarningPreset = "relaxed"
DEMO_MEDIA_RESOLUTION_WARNING_PRESET: MediaResolutionWarningPreset = "off"


class AlbumBase(SQLModel):
    """User-editable settings."""

    title: str = Field(max_length=255)
    subtitle: str = Field(max_length=255)
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
    front_cover_photo: str = Field(max_length=255)
    back_cover_photo: str = Field(max_length=255)
    font: str = Field(
        default=DEFAULT_FONT,
        sa_column=Column(String(100), nullable=False, default=DEFAULT_FONT),
    )
    body_font: str = Field(
        default=DEFAULT_BODY_FONT,
        sa_column=Column(String(100), nullable=False, default=DEFAULT_BODY_FONT),
    )
    safe_margin_mm: int = Field(default=5)
    media_resolution_warning_preset: MediaResolutionWarningPreset = Field(
        default=DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
        sa_column=Column(
            String(20),
            nullable=False,
            default=DEFAULT_MEDIA_RESOLUTION_WARNING_PRESET,
        ),
    )


@all_optional
class AlbumUpdate(AlbumBase):
    pass


class AlbumMeta(AlbumBase):
    """GET/PATCH response - everything except media."""

    uid: int = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    id: str = Field(primary_key=True)
    colors: dict[CountryCode, HexColor] = Field(
        sa_column=Column(PydanticJSON(dict[CountryCode, HexColor]), nullable=False)
    )
    upgraded_media: dict[MediaName, GoogleMediaId] = Field(
        default_factory=dict,
        sa_column=Column(
            PydanticJSON(dict[MediaName, GoogleMediaId]),
            nullable=False,
            server_default="{}",
        ),
    )


class Album(AlbumMeta, table=True):
    """Full DB row. Only adds media - no relationships."""

    media: list[Media] = Field(
        default_factory=list,
        sa_column=Column(PydanticJSON(list[Media]), nullable=False),
    )


class PrintBundle(BaseModel):
    """Everything needed for PDF rendering in one response."""

    album: Album
    steps: list[Step]
    segments: list[Segment]
    total_distance_km: float
