from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator, StringConstraints
from sqlmodel import JSON, Column, Field, SQLModel

from app.core.config import settings
from app.core.db import PydanticJSON, all_optional
from app.models.polarsteps import Location


def _normalize_locale(v: object) -> object:
    """Accept both xx_XX and xx-XX, normalize to BCP 47 (xx-XX)."""
    return v.replace("_", "-") if isinstance(v, str) else v


Locale = Annotated[
    str,
    BeforeValidator(_normalize_locale),
    StringConstraints(pattern=r"^[a-z]{2}(-[A-Z]{2})?$", min_length=2, max_length=5),
]


class UserBase(SQLModel):
    locale: Locale
    unit_is_km: bool
    temperature_is_celsius: bool


class UserCreate(UserBase):
    id: int = Field(primary_key=True)
    first_name: str = Field(max_length=255)
    last_name: str = Field(max_length=255)
    profile_image_path: str | None = Field(default=None, max_length=500)
    living_location: Location = Field(
        sa_column=Column(PydanticJSON(Location), nullable=False)
    )

    @property
    def folder(self) -> Path:
        return settings.USERS_FOLDER / str(self.id)

    @property
    def trips_folder(self) -> Path:
        return self.folder / "trip"


@all_optional
class UserUpdate(UserBase):
    pass


class User(UserCreate, table=True):
    album_ids: list[str] = Field(sa_column=Column(JSON, nullable=False))
