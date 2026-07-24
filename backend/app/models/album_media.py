from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

# Pydantic resolves this annotation while constructing the SQLModel.
from pydantic.json_schema import SkipJsonSchema  # noqa: TC002
from sqlmodel import Field, SQLModel


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
        sa_column=sa.Column(sa.JSON(), nullable=True),
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
        sa_column=sa.Column(sa.JSON(), nullable=True),
    )
    upgrade_candidate: bool
    created_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False)
    )
    expires_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False)
    )
