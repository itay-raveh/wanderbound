"""Drop album-level content fields.

Revision ID: 7f4c2a9d6b10
Revises: 3a1b9d7f6c20
Create Date: 2026-06-20 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "7f4c2a9d6b10"
down_revision = "3a1b9d7f6c20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("album", "title")
    op.drop_column("album", "subtitle")
    op.drop_column("album", "front_cover_photo")
    op.drop_column("album", "back_cover_photo")


def downgrade() -> None:
    op.add_column("album", sa.Column("back_cover_photo", sa.String(255)))
    op.add_column("album", sa.Column("front_cover_photo", sa.String(255)))
    op.add_column("album", sa.Column("subtitle", sa.String(255)))
    op.add_column("album", sa.Column("title", sa.String(255)))
