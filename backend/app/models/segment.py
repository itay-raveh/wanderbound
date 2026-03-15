from enum import StrEnum
from typing import NamedTuple

from sqlalchemy import ForeignKeyConstraint
from sqlmodel import Column, Field, SQLModel

from app.core.db import PydanticJSON
from app.models.ids import AlbumId, UserId
from app.models.polarsteps import Point


class SegmentKind(StrEnum):
    flight = "flight"
    hike = "hike"
    walking = "walking"
    driving = "driving"


class SegmentData(NamedTuple):
    """Pipeline output from GPS segmentation (not a DB model)."""

    kind: SegmentKind
    points: list[Point]


class Segment(SQLModel, table=True):
    __table_args__ = (
        ForeignKeyConstraint(
            ["uid", "aid"], ["album.uid", "album.id"], ondelete="CASCADE"
        ),
    )

    uid: UserId = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    aid: AlbumId = Field(primary_key=True)
    start_time: float = Field(primary_key=True)
    end_time: float = Field(primary_key=True)
    kind: SegmentKind
    points: list[Point] = Field(
        sa_column=Column(PydanticJSON(list[Point]), nullable=False)
    )
