from pathlib import Path
from typing import Annotated

from pydantic import StringConstraints
from sqlmodel import JSON, Column, Field, SQLModel

from app.core.config import settings
from app.core.db import PydanticJSON, all_optional
from app.models.polarsteps import Location
from app.models.types import AlbumId, UserId

Locale = Annotated[
    str, StringConstraints(pattern=r"^[a-z]{2}_[A-Z]{2}$", min_length=5, max_length=5)
]


class UserBase(SQLModel):
    first_name: str = Field(max_length=255)
    last_name: str = Field(max_length=255)
    profile_image_path: str | None = Field(default=None, max_length=500)
    living_location: Location = Field(
        sa_column=Column(PydanticJSON(Location), nullable=False)
    )
    locale: Locale
    unit_is_km: bool
    temperature_is_celsius: bool


@all_optional
class UserUpdate(UserBase):
    pass


class User(UserBase, table=True):
    id: UserId = Field(primary_key=True)
    album_ids: list[AlbumId] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )

    @property
    def folder(self) -> Path:
        return settings.USERS_FOLDER / str(self.id)

    @property
    def trips_folder(self) -> Path:
        return self.folder / "trip"
