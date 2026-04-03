from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import sqlalchemy as sa
from pydantic import (
    BaseModel,
    BeforeValidator,
    HttpUrl,
    StringConstraints,
    computed_field,
)
from sqlmodel import JSON, Column, Field, SQLModel

from app.core.config import get_settings
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
    first_name: str = Field(max_length=255)
    locale: Locale
    unit_is_km: bool
    temperature_is_celsius: bool


@all_optional
class UserUpdate(UserBase):
    pass


class PSUser(UserBase):
    """Parsed from user/user.json in the Polarsteps data export ZIP."""

    id: int
    living_location: Location | None = None


AuthProvider = Literal["google", "microsoft"]


class OAuthIdentity(BaseModel):
    sub: str
    first_name: str
    picture: HttpUrl | None = None
    provider: AuthProvider


class User(UserBase, table=True):
    __table_args__ = (
        sa.CheckConstraint(
            "google_sub IS NOT NULL OR microsoft_sub IS NOT NULL",
            name="ck_user_has_provider",
        ),
    )

    id: int = Field(primary_key=True)
    google_sub: str | None = Field(default=None, unique=True, index=True)
    microsoft_sub: str | None = Field(default=None, unique=True, index=True)
    profile_image_url: str | None = Field(default=None, max_length=500)
    living_location: Location | None = Field(
        default=None, sa_column=Column(PydanticJSON(Location), nullable=True)
    )
    album_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    last_active_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(
            "last_active_at",
            type_=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    @computed_field
    @property
    def has_data(self) -> bool:
        return self.folder.exists()

    @property
    def folder(self) -> Path:
        return get_settings().USERS_FOLDER / str(self.id)

    @property
    def trips_folder(self) -> Path:
        return self.folder / "trip"
