from pydantic import BaseModel
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from app.core.db import all_optional
from app.models.geo import CountryCode, HexColor

from .segment import Segment
from .step import Step
from .types import AlbumId, UserId


class AlbumBase(SQLModel):
    title: str = Field(max_length=255)
    subtitle: str = Field(max_length=255)
    steps_ranges: str = Field(max_length=255)
    maps_ranges: str | None = Field(default=None, max_length=255)
    front_cover_photo: str = Field(max_length=255)
    back_cover_photo: str = Field(max_length=255)


@all_optional
class AlbumUpdate(AlbumBase):
    pass


class Album(AlbumBase, table=True):
    uid: UserId = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    id: AlbumId = Field(primary_key=True)

    steps: list[Step] = Relationship(
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "Step.idx"},
    )
    segments: list[Segment] = Relationship(
        cascade_delete=True,
        sa_relationship_kwargs={"order_by": "Segment.start_time"},
    )
    colors: dict[CountryCode, HexColor] = Field(sa_column=Column(JSON, nullable=False))
    orientations: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )


class AlbumData(BaseModel):
    steps: list[Step]
    segments: list[Segment]
