from datetime import datetime
from typing import Self
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, computed_field, model_validator
from sqlalchemy import ForeignKeyConstraint
from sqlmodel import Column, Field, SQLModel

from app.core.db import PydanticJSON, all_optional
from app.models.album_media import StepPageKind
from app.models.polarsteps import Location
from app.models.weather import Weather


class StepBase(SQLModel):
    name: str = Field(max_length=255)
    description: str


@all_optional
class StepUpdate(StepBase):
    pass


class StepPageLayout(SQLModel):
    kind: StepPageKind
    media: list[str]

    @model_validator(mode="after")
    def validate_panorama_spread_media(self) -> Self:
        if self.kind == "panorama_spread" and len(self.media) != 1:
            raise ValueError("A panorama spread must contain exactly one media item")
        return self


class StepMediaLayout(SQLModel):
    cover: str | None = Field(max_length=255)
    pages: list[StepPageLayout]
    unused: list[str]


class Step(StepBase, table=True):
    __table_args__ = (
        ForeignKeyConstraint(
            ["uid", "aid"], ["album.uid", "album.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["uid", "aid", "cover_media_name"],
            ["album_media.uid", "album_media.aid", "album_media.name"],
        ),
    )

    uid: int = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    aid: str = Field(primary_key=True)
    id: int = Field(primary_key=True)

    timestamp: float
    timezone_id: str = Field(max_length=255)
    location: Location = Field(sa_column=Column(PydanticJSON(Location), nullable=False))
    elevation: int
    weather: Weather = Field(sa_column=Column(PydanticJSON(Weather), nullable=False))
    cover_media_name: str | None = Field(default=None, max_length=255)

    @computed_field(return_type=AwareDatetime)
    @property
    def datetime(self) -> AwareDatetime:
        return datetime.fromtimestamp(self.timestamp, tz=ZoneInfo(self.timezone_id))


class StepRead(StepBase, StepMediaLayout):
    uid: int
    aid: str
    id: int

    timestamp: float
    timezone_id: str
    location: Location
    elevation: int
    weather: Weather

    @computed_field(return_type=AwareDatetime)
    @property
    def datetime(self) -> AwareDatetime:
        return datetime.fromtimestamp(self.timestamp, tz=ZoneInfo(self.timezone_id))
