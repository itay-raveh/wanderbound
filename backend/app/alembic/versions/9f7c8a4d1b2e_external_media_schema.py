"""external media schema

Revision ID: 9f7c8a4d1b2e
Revises: dcb0d4e8f8b3
Create Date: 2026-05-13 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "9f7c8a4d1b2e"
down_revision = "dcb0d4e8f8b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "album_media_source_ref",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "google_media_id",
            sqlmodel.sql.sqltypes.AutoString(length=256),
            nullable=True,
        ),
        sa.Column(
            "mime_type",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uid", "aid"], ["album.uid", "album.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uid"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "album_media",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "storage_path",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uid", "aid"], ["album.uid", "album.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_ref_id"], ["album_media_source_ref.id"]),
        sa.ForeignKeyConstraint(["uid"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uid", "aid", "name"),
        sa.UniqueConstraint("uid", "aid", "name", name="uq_album_media_name"),
    )
    op.create_table(
        "album_media_undo_snapshot",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "media_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "snapshot_path",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "media_name"],
            ["album_media.uid", "album_media.aid", "album_media.name"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uid", "aid", "media_name"),
    )
    op.drop_column("album", "upgraded_media")
    op.drop_column("album", "media")


def downgrade() -> None:
    op.add_column(
        "album",
        sa.Column("media", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "album",
        sa.Column("upgraded_media", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.drop_table("album_media_undo_snapshot")
    op.drop_table("album_media")
    op.drop_table("album_media_source_ref")
