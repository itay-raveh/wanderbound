"""add panorama undo state

Revision ID: e4f6a8b0c2d3
Revises: d3e5f7a9b1c2
Create Date: 2026-07-26 15:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "e4f6a8b0c2d3"
down_revision = "d3e5f7a9b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "album_media_undo_snapshot", sa.Column("panorama", sa.JSON(), nullable=True)
    )
    op.add_column(
        "album_media_undo_snapshot",
        sa.Column("original_snapshot_path", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("album_media_undo_snapshot", "original_snapshot_path")
    op.drop_column("album_media_undo_snapshot", "panorama")
