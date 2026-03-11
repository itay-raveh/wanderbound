import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path, PurePath
from typing import Any, BinaryIO, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, computed_field
from safezip import safe_extract
from sqlalchemy import ForeignKeyConstraint, TypeDecorator
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from app.core.config import settings
from app.logic.country_colors import CountryCode, HexColor
from app.logic.weather import Weather
from app.models.trips import Location


def _json_default(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, PurePath):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class PydanticJSON(TypeDecorator[Any]):
    """JSON column that deserializes into a Pydantic model."""

    impl = JSON
    cache_ok = True

    def __init__(self, model_class: type[BaseModel]) -> None:
        super().__init__()
        self.model_class = model_class

    def process_result_value(self, value: Any, dialect: Any) -> Any:  # noqa: ARG002
        if value is None:
            return None
        if isinstance(value, dict):
            return self.model_class.model_validate(value)
        return value


engine = create_async_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    json_serializer=lambda obj: json.dumps(obj, default=_json_default),
    json_deserializer=json.loads,
)


class User(SQLModel, table=True):
    id: int = Field(primary_key=True)
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)
    profile_image_path: str | None = Field(default=None, max_length=500)
    living_location: Location = Field(
        sa_column=Column(PydanticJSON(Location), nullable=False)
    )
    locale: str = Field(regex="^[a-z]{2}_[A-Z]{2}$", max_length=5)
    unit_is_km: bool
    temperature_is_celsius: bool

    albums: list[Album] = Relationship(back_populates="user", cascade_delete=True)

    @classmethod
    def from_zip_upload(cls, file: BinaryIO) -> Self:
        """Build a new user from a Polarsteps ZIP.

        Args:
            file: Uploaded ``user_data.zip``.

        Returns:
            Created User.

        Raises:
            BadZipFile: See `safezip.safe_extract`.
            SafezipError: See `safezip.safe_extract`.
            OSError: The user directory exists.
        """
        # Extract the ZIP into a unique tmp folder
        folder = Path(tempfile.mkdtemp(dir=settings.USERS_FOLDER))
        safe_extract(file, folder)

        # Create the user from the folder
        user = cls.model_validate_json((folder / "user" / "user.json").read_bytes())

        # Rename the tmp folder
        if user.folder.exists():
            shutil.rmtree(user.folder)
        folder.rename(user.folder)

        return user

    @property
    def folder(self) -> Path:
        return settings.USERS_FOLDER / str(self.id)

    @property
    def trips_folder(self) -> Path:
        return self.folder / "trip"


AlbumId = str


class AlbumSettings(SQLModel):
    title: str = Field(max_length=255)
    subtitle: str = Field(max_length=255)
    steps_ranges: str = Field(max_length=255)
    maps_ranges: str | None = Field(default=None, max_length=255)
    front_cover_photo: str = Field(
        max_length=255,
        description="Either a URL, or path to one of the photos form the trip",
    )
    back_cover_photo: str = Field(
        max_length=255,
        description="Either a URL, or path to one of the photos form the trip",
    )


class Album(AlbumSettings, table=True):
    uid: int = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    id: AlbumId = Field(primary_key=True, max_length=255)

    user: User = Relationship(back_populates="albums")
    steps: list[Step] = Relationship(back_populates="album", cascade_delete=True)
    colors: dict[CountryCode, HexColor] = Field(sa_column=Column(JSON, nullable=False))


StepIdx = int


class StepLayout(SQLModel):
    cover: Path = Field(sa_column=Column(JSON, nullable=False))
    pages: list[list[Path]] = Field(sa_column=Column(JSON, nullable=False))
    unused: list[Path] = Field(sa_column=Column(JSON, nullable=False))


class Step(StepLayout, table=True):
    __table_args__ = (
        ForeignKeyConstraint(
            ["uid", "aid"], ["album.uid", "album.id"], ondelete="CASCADE"
        ),
    )

    uid: int = Field(primary_key=True, foreign_key="user.id")
    aid: AlbumId = Field(primary_key=True)
    idx: StepIdx = Field(primary_key=True)

    album: Album = Relationship(back_populates="steps")
    name: str = Field(max_length=255)
    description: str
    timestamp: float
    timezone_id: str = Field(max_length=255)
    location: Location = Field(sa_column=Column(PydanticJSON(Location), nullable=False))
    elevation: int
    weather: Weather = Field(sa_column=Column(PydanticJSON(Weather), nullable=False))

    @computed_field(return_type=datetime)
    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=ZoneInfo(self.timezone_id))
