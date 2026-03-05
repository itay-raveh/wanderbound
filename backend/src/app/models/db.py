# ruff: noqa: TC003, TC001
import datetime
import pickle
from pathlib import Path
from typing import BinaryIO, Self
from zoneinfo import ZoneInfo

from pydantic import computed_field
from safezip import safe_extract
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from app.core.settings import settings
from app.logic.data.country_colors import CountryCode, HexColor
from app.logic.data.weather import Weather
from app.models.trips import Location

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
    id: int = Field(primary_key=True)
    first_name: str
    last_name: str
    living_location: Location = Field(sa_column=Column(JSON))
    locale: str = Field(regex="^[a-z]{2}_[A-Z]{2}$")
    unit_is_km: bool
    temperature_is_celsius: bool

    albums: list[Album] = Relationship(back_populates="user", cascade_delete=True)

    @classmethod
    def from_zip_upload(cls, file: BinaryIO) -> Self:
        # Extract the ZIP into a tmp folder
        folder = settings.users_dir / "tmp"
        safe_extract(file, folder)

        # Create the user from the folder and rename the folder with its ID
        user = cls.model_validate_json((folder / "user" / "user.json").read_bytes())
        folder.rename(user.folder)

        # Remove the now unneeded user data
        (user.folder / "user" / "user.json").unlink()
        (user.folder / "user").rmdir()

        return user

    @property
    def folder(self) -> Path:
        return settings.users_dir / str(self.id)

    @property
    def trips_folder(self) -> Path:
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


class Album(AlbumSettings, table=True):
    uid: int = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    id: AlbumId = Field(primary_key=True)

    user: User = Relationship(back_populates="albums")
    steps: list[Step] = Relationship(back_populates="album", cascade_delete=True)

    colors: dict[CountryCode, HexColor] = Field(sa_column=Column(JSON))


StepIdx = int


class StepLayout(SQLModel):
    cover: Path = Field(sa_column=Column(JSON))
    pages: list[list[Path]] = Field(sa_column=Column(JSON))
    unused: list[Path] = Field(sa_column=Column(JSON))


class Step(StepLayout, table=True):
    uid: int = Field(primary_key=True, foreign_key="user.id")
    aid: AlbumId = Field(primary_key=True, foreign_key="album.id")
    idx: StepIdx = Field(primary_key=True)

    album: Album = Relationship(back_populates="steps")

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
