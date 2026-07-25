"""add perceptual media hashes

Revision ID: 3a6e5f8b1c2d
Revises: 7c2a9f4d8e10
Create Date: 2026-07-24 04:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "3a6e5f8b1c2d"
down_revision = "7c2a9f4d8e10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "album_media",
        sa.Column("perceptual_hashes", sa.JSON(), nullable=True),
    )
    op.add_column(
        "album_media_undo_snapshot",
        sa.Column("perceptual_hashes", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("album_media_undo_snapshot", "perceptual_hashes")
    op.drop_column("album_media", "perceptual_hashes")
