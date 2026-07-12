"""Move album content into chapters.

Revision ID: 3a1b9d7f6c20
Revises: 1f6d2e8c9a0b
Create Date: 2026-06-15 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "3a1b9d7f6c20"
down_revision = "1f6d2e8c9a0b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "album",
        sa.Column("chapters", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.drop_column("album", "title")
    op.drop_column("album", "subtitle")
    op.drop_column("album", "front_cover_photo")
    op.drop_column("album", "back_cover_photo")


def downgrade() -> None:
    op.add_column("album", sa.Column("back_cover_photo", sa.String(255)))
    op.add_column("album", sa.Column("front_cover_photo", sa.String(255)))
    op.add_column("album", sa.Column("subtitle", sa.String(255)))
    op.add_column("album", sa.Column("title", sa.String(255)))
    op.drop_column("album", "chapters")
