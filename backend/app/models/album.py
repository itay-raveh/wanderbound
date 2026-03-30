from __future__ import annotations

from datetime import date

from pydantic import BaseModel, field_validator
from sqlmodel import Column, Field, SQLModel

from app.core.db import PydanticJSON, all_optional
from app.logic.layout.media import Media
from app.models.polarsteps import CountryCode, HexColor
from app.models.segment import Segment
from app.models.step import Step

type DateRange = tuple[date, date]

ALLOWED_FONTS = {"Frank Ruhl Libre", "Assistant"}
DEFAULT_FONT = "Assistant"
DEFAULT_BODY_FONT = "Frank Ruhl Libre"


def _validate_font(v: str, field_name: str) -> str:
    if v not in ALLOWED_FONTS:
        msg = f"{field_name} must be one of {ALLOWED_FONTS}"
        raise ValueError(msg)
    return v


class AlbumBase(SQLModel):
    """User-editable settings."""

    title: str = Field(max_length=255)
    subtitle: str = Field(max_length=255)
    excluded_steps: list[int] = Field(
        sa_column=Column(PydanticJSON(list[int]), nullable=False),
        default_factory=list,
    )
    maps_ranges: list[DateRange] = Field(
        sa_column=Column(PydanticJSON(list[DateRange]), nullable=False),
        default_factory=list,
    )
    front_cover_photo: str = Field(max_length=255)
    back_cover_photo: str = Field(max_length=255)
    font: str = Field(default=DEFAULT_FONT, max_length=100)
    body_font: str = Field(default=DEFAULT_BODY_FONT, max_length=100)

    @field_validator("font")
    @classmethod
    def _validate_font(cls, v: str) -> str:
        return _validate_font(v, "font")

    @field_validator("body_font")
    @classmethod
    def _validate_body_font(cls, v: str) -> str:
        return _validate_font(v, "body_font")


@all_optional
class AlbumUpdate(AlbumBase):
    pass


class AlbumMeta(AlbumBase):
    """GET/PATCH response — everything except media."""

    uid: int = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    id: str = Field(primary_key=True)
    colors: dict[CountryCode, HexColor] = Field(
        sa_column=Column(PydanticJSON(dict[CountryCode, HexColor]), nullable=False)
    )


class Album(AlbumMeta, table=True):
    """Full DB row. Only adds media — no relationships."""

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
