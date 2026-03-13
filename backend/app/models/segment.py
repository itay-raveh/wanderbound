from sqlalchemy import ForeignKeyConstraint
from sqlmodel import Column, Field, SQLModel

from app.core.db import PydanticJSON
from app.models.polarsteps import Point
from app.models.types import AlbumId, SegmentKind, UserId


class SegmentBase(SQLModel):
    kind: SegmentKind
    points: list[Point] = Field(
        sa_column=Column(PydanticJSON(list[Point]), nullable=False)
    )


class Segment(SegmentBase, table=True):
    __table_args__ = (
        ForeignKeyConstraint(
            ["uid", "aid"], ["album.uid", "album.id"], ondelete="CASCADE"
        ),
    )

    uid: UserId = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    aid: AlbumId = Field(primary_key=True)
    start_time: float = Field(primary_key=True)
    end_time: float = Field(primary_key=True)
