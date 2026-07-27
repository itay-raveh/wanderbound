from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import sqlalchemy as sa

# Pydantic resolves this annotation while constructing the SQLModel.
from pydantic import BaseModel, Field as PydanticField, computed_field
from pydantic.json_schema import SkipJsonSchema  # noqa: TC002
from sqlmodel import Field, SQLModel

from app.core.db import PydanticJSON

type StepPageKind = Literal["grid", "panorama_spread"]
MIN_PANORAMA_ASPECT_RATIO = 2


def is_panorama_size(width: int, height: int) -> bool:
    return height > 0 and width / height >= MIN_PANORAMA_ASPECT_RATIO


def panorama_captured_fov(width: int, height: int) -> float:
    return min(359, 90 * width / height)


class PanoramaConfig(BaseModel):
    yaw: float = PydanticField(default=0, ge=-360, le=360)
    pitch: float = PydanticField(default=0, ge=-90, le=90)
    perspective_fov: float = PydanticField(default=70, gt=0, lt=180)
    zoom: float = PydanticField(default=1, ge=1, le=3)
    aspect_ratio: float = PydanticField(default=2, gt=0, le=10)


class AlbumMedia(SQLModel, table=True):
    __tablename__ = "album_media"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["uid", "aid"],
            ["album.uid", "album.id"],
            ondelete="CASCADE",
        ),
    )

    uid: int = Field(primary_key=True, foreign_key="user.id", ondelete="CASCADE")
    aid: str = Field(primary_key=True)
    name: str = Field(primary_key=True, max_length=255)
    kind: str = Field(sa_column=sa.Column(sa.String(16), nullable=False))
    width: int
    height: int
    byte_size: int = Field(sa_column=sa.Column(sa.BigInteger(), nullable=False))
    perceptual_hashes: SkipJsonSchema[list[str] | None] = Field(
        default=None,
        exclude=True,
        sa_column=sa.Column(sa.JSON(none_as_null=True), nullable=True),
    )
    panorama: PanoramaConfig | None = Field(
        default=None,
        sa_column=sa.Column(PydanticJSON(PanoramaConfig), nullable=True),
    )
    upgrade_candidate: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )

    @computed_field
    @property
    def panorama_candidate(self) -> bool:
        return self.kind == "photo" and is_panorama_size(self.width, self.height)


class StepPageMedia(SQLModel, table=True):
    __tablename__ = "step_page_media"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["uid", "aid", "step_id"],
            ["step.uid", "step.aid", "step.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "media_name"],
            ["album_media.uid", "album_media.aid", "album_media.name"],
            ondelete="CASCADE",
        ),
    )

    uid: int = Field(primary_key=True)
    aid: str = Field(primary_key=True)
    step_id: int = Field(primary_key=True)
    page_index: int = Field(primary_key=True)
    position_index: int = Field(primary_key=True)
    media_name: str = Field(max_length=255)
    page_kind: StepPageKind = Field(
        default="grid", sa_column=sa.Column(sa.String(16), nullable=False)
    )


class StepUnusedMedia(SQLModel, table=True):
    __tablename__ = "step_unused_media"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["uid", "aid", "step_id"],
            ["step.uid", "step.aid", "step.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "media_name"],
            ["album_media.uid", "album_media.aid", "album_media.name"],
            ondelete="CASCADE",
        ),
    )

    uid: int = Field(primary_key=True)
    aid: str = Field(primary_key=True)
    step_id: int = Field(primary_key=True)
    position_index: int = Field(primary_key=True)
    media_name: str = Field(max_length=255)


class AlbumMediaUndoSnapshot(SQLModel, table=True):
    __tablename__ = "album_media_undo_snapshot"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["uid", "aid", "media_name"],
            ["album_media.uid", "album_media.aid", "album_media.name"],
            ondelete="CASCADE",
        ),
    )

    uid: int = Field(primary_key=True)
    aid: str = Field(primary_key=True)
    media_name: str = Field(primary_key=True, max_length=255)
    snapshot_path: str = Field(max_length=255)
    perceptual_hashes: SkipJsonSchema[list[str] | None] = Field(
        default=None,
        exclude=True,
        sa_column=sa.Column(sa.JSON(none_as_null=True), nullable=True),
    )
    panorama: PanoramaConfig | None = Field(
        default=None,
        sa_column=sa.Column(PydanticJSON(PanoramaConfig), nullable=True),
    )
    upgrade_candidate: bool
    created_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False)
    )
    expires_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False)
    )
