from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import sqlalchemy as sa

# Pydantic resolves this annotation while constructing the SQLModel.
from pydantic import BaseModel, Field as PydanticField, computed_field, model_validator
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


class PhotoEdit(BaseModel):
    angle: float = PydanticField(ge=-180, le=180)
    x: float = PydanticField(ge=0, le=1)
    y: float = PydanticField(ge=0, le=1)
    width: float = PydanticField(gt=0, le=1)
    height: float = PydanticField(gt=0, le=1)

    @model_validator(mode="after")
    def within_canvas(self) -> PhotoEdit:
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("Crop exceeds the rotated image bounds")
        return self


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
    photo_edit: PhotoEdit | None = Field(
        default=None,
        sa_column=sa.Column(PydanticJSON(PhotoEdit), nullable=True),
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


class StepPage(SQLModel, table=True):
    __tablename__ = "step_page"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["uid", "aid", "step_id"],
            ["step.uid", "step.aid", "step.id"],
            ondelete="CASCADE",
        ),
    )

    uid: int = Field(primary_key=True)
    aid: str = Field(primary_key=True)
    step_id: int = Field(primary_key=True)
    id: str = Field(primary_key=True, max_length=36)
    position_index: int
    page_kind: StepPageKind = Field(
        default="grid", sa_column=sa.Column(sa.String(16), nullable=False)
    )


class StepPageSlot(SQLModel, table=True):
    __tablename__ = "step_page_slot"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["uid", "aid", "step_id", "page_id"],
            ["step_page.uid", "step_page.aid", "step_page.step_id", "step_page.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "media_name"],
            ["album_media.uid", "album_media.aid", "album_media.name"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "(kind = 'photo' AND media_name IS NOT NULL AND text_content IS NULL) "
            "OR (kind = 'text' AND media_name IS NULL AND text_content IS NOT NULL)",
            name="step_page_slot_content",
        ),
    )

    uid: int = Field(primary_key=True)
    aid: str = Field(primary_key=True)
    step_id: int = Field(primary_key=True)
    id: str = Field(primary_key=True, max_length=36)
    page_id: str = Field(max_length=36)
    position_index: int
    kind: str = Field(sa_column=sa.Column(sa.String(16), nullable=False))
    media_name: str | None = Field(default=None, max_length=255)
    text_content: str | None = Field(default=None, sa_column=sa.Column(sa.Text()))
    frame_orientation: str = Field(
        default="landscape", sa_column=sa.Column(sa.String(16), nullable=False)
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
    photo_edit: PhotoEdit | None = Field(
        default=None,
        sa_column=sa.Column(PydanticJSON(PhotoEdit), nullable=True),
    )
    upgrade_candidate: bool
    created_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False)
    )
    expires_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False)
    )
