from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, computed_field
from sqlalchemy import ForeignKeyConstraint
from sqlmodel import JSON, Column, Field, SQLModel

from app.core.db import PydanticJSON, all_optional
from app.models.ids import AlbumId, StepIdx, UserId
from app.models.polarsteps import Location
from app.models.weather import Weather


class StepBase(SQLModel):
    name: str = Field(max_length=255)
    description: str
    cover: str | None = None
    pages: list[list[str]] = Field(sa_column=Column(JSON, nullable=False))
    unused: list[str] = Field(sa_column=Column(JSON, nullable=False))


@all_optional
class StepUpdate(StepBase):
    pass


class Step(StepBase, table=True):
    __table_args__ = (
        ForeignKeyConstraint(
            ["uid", "aid"], ["album.uid", "album.id"], ondelete="CASCADE"
        ),
    )

    uid: UserId = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    aid: AlbumId = Field(primary_key=True)
    idx: StepIdx = Field(primary_key=True)

    timestamp: float
    timezone_id: str = Field(max_length=255)
    location: Location = Field(sa_column=Column(PydanticJSON(Location), nullable=False))
    elevation: int
    weather: Weather = Field(sa_column=Column(PydanticJSON(Weather), nullable=False))

    @computed_field(return_type=AwareDatetime)
    @property
    def datetime(self) -> AwareDatetime:
        return datetime.fromtimestamp(self.timestamp, tz=ZoneInfo(self.timezone_id))
