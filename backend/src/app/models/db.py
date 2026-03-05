# ruff: noqa: TC003, TC001
import datetime
import pickle
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import UUID4, computed_field
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import JSON, Column, Field, SQLModel

from app.core.settings import settings
from app.logic.data.country_colors import CountryCode, HexColor
from app.logic.data.weather import Weather
from app.models.polarsteps import Location

engine = create_async_engine(
    str(settings.db_conn_uri),
    # To allow JSON columns with Pydantic models:
    json_serializer=pickle.dumps,
    json_deserializer=pickle.loads,
)


async def init_db() -> None:
    # noinspection PyTypeChecker
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


class User(SQLModel, table=True):
    id: UUID4 = Field(default_factory=uuid4, primary_key=True)

    @property
    def folder(self) -> Path:
        return settings.users_dir / str(self.id)

    @property
    def trip_folder(self) -> Path:
        return self.folder / "trip"


AlbumId = str


class AlbumSettings(SQLModel):
    title: str
    subtitle: str
    steps_ranges: str
    maps_ranges: str | None = None
    front_cover_photo: str = Field(
        description="Either a URL, or path to one of the photos form the trip"
    )
    back_cover_photo: str = Field(
        description="Either a URL, or path to one of the photos form the trip"
    )
    use_location: bool = False


class Album(AlbumSettings, table=True):
    uid: UUID4 = Field(primary_key=True, foreign_key="user.id")
    id: AlbumId = Field(primary_key=True)

    colors: dict[CountryCode, HexColor] = Field(sa_column=Column(JSON))


StepIdx = int


class StepLayout(SQLModel):
    cover: Path = Field(sa_column=Column(JSON))
    pages: list[list[Path]] = Field(sa_column=Column(JSON))
    unused: list[Path] = Field(sa_column=Column(JSON))


class Step(StepLayout, table=True):
    uid: UUID4 = Field(primary_key=True, foreign_key="user.id")
    aid: AlbumId = Field(primary_key=True, foreign_key="album.id")
    idx: StepIdx = Field(primary_key=True)

    name: str
    description: str
    timestamp: float
    timezone_id: str
    location: Location = Field(sa_column=Column(JSON))
    elevation: int
    weather: Weather = Field(sa_column=Column(JSON))

    @computed_field(return_type=datetime.datetime)
    @property
    def datetime(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.timestamp, tz=ZoneInfo(self.timezone_id))
