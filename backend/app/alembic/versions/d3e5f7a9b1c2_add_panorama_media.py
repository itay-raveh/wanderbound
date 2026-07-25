"""add panorama media

Revision ID: d3e5f7a9b1c2
Revises: c2d4e6f8a0b1
Create Date: 2026-07-26 14:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d3e5f7a9b1c2"
down_revision = "c2d4e6f8a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("album_media", sa.Column("panorama", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("album_media", "panorama")
