from datetime import date

from pydantic import BaseModel
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from app.core.db import PydanticJSON, all_optional
from app.models.polarsteps import CountryCode, HexColor

from .segment import Segment
from .step import Step

type DateRange = tuple[date, date]


class AlbumBase(SQLModel):
    title: str = Field(max_length=255)
    subtitle: str = Field(max_length=255)
    steps_ranges: list[DateRange] = Field(
        sa_column=Column(PydanticJSON(list[DateRange]), nullable=False),
    )
    maps_ranges: list[DateRange] = Field(
        sa_column=Column(PydanticJSON(list[DateRange]), nullable=False),
        default_factory=list,
    )
    front_cover_photo: str = Field(max_length=255)
    back_cover_photo: str = Field(max_length=255)


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
