from datetime import date

from pydantic import BaseModel, field_validator
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from app.core.db import PydanticJSON, all_optional
from app.models.polarsteps import CountryCode, HexColor

from .segment import Segment
from .step import Step

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


class Album(AlbumBase, table=True):
    uid: int = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    id: str = Field(primary_key=True)

    steps: list[Step] = Relationship(
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "[Step.timestamp, Step.id]"},
    )
    segments: list[Segment] = Relationship(
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "Segment.start_time"},
    )
    colors: dict[CountryCode, HexColor] = Field(sa_column=Column(JSON, nullable=False))
    media: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )


class AlbumData(BaseModel):
    steps: list[Step]
    segments: list[Segment]
