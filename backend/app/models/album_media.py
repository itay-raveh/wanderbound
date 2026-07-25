from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import sqlalchemy as sa

# Pydantic resolves this annotation while constructing the SQLModel.
from pydantic import BaseModel, Field as PydanticField, model_validator
from pydantic.json_schema import SkipJsonSchema  # noqa: TC002
from sqlmodel import Field, SQLModel

from app.core.db import PydanticJSON

type StepPageKind = Literal["grid", "panorama_spread"]
type PanoramaStatus = Literal["active", "suggested", "disabled"]
type PanoramaDetection = Literal["gpano", "dimensions"]


class PanoramaConfig(BaseModel):
    status: PanoramaStatus
    detection: PanoramaDetection
    source_width: int = PydanticField(gt=0)
    source_height: int = PydanticField(gt=0)
    cropped_area_width: int | None = PydanticField(default=None, gt=0)
    cropped_area_height: int | None = PydanticField(default=None, gt=0)
    cropped_area_left: int | None = PydanticField(default=None, ge=0)
    cropped_area_top: int | None = None
    full_pano_width: int | None = PydanticField(default=None, gt=0)
    full_pano_height: int | None = PydanticField(default=None, gt=0)
    captured_fov: float = PydanticField(gt=0, lt=360)
    yaw: float = PydanticField(default=0, ge=-360, le=360)
    pitch: float = PydanticField(default=0, ge=-90, le=90)
    perspective_fov: float = PydanticField(default=70, gt=0, lt=180)
    zoom: float = PydanticField(default=1, ge=1)
    original_path: str | None = None
    revision: int = PydanticField(default=1, gt=0)

    @model_validator(mode="after")
    def validate_cropped_area(self) -> PanoramaConfig:
        if (
            self.cropped_area_width is not None
            and self.full_pano_width is not None
            and self.cropped_area_width > self.full_pano_width
        ):
            raise ValueError("Cropped panorama width exceeds the full panorama")
        if (
            self.cropped_area_height is not None
            and self.full_pano_height is not None
            and self.cropped_area_top is not None
            and self.cropped_area_top + self.cropped_area_height > self.full_pano_height
        ):
            raise ValueError("Cropped panorama height exceeds the full panorama")
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
    upgrade_candidate: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )


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
    page_index: int = Field(primary_key=True)
    kind: StepPageKind = Field(sa_column=sa.Column(sa.String(16), nullable=False))


class StepPageMedia(SQLModel, table=True):
    __tablename__ = "step_page_media"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["uid", "aid", "step_id"],
            ["step.uid", "step.aid", "step.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "step_id", "page_index"],
            [
                "step_page.uid",
                "step_page.aid",
                "step_page.step_id",
                "step_page.page_index",
            ],
            name="fk_step_page_media_page",
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
    upgrade_candidate: bool
    created_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False)
    )
    expires_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False)
    )
