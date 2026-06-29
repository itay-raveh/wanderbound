"""Add album chapters.

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


def downgrade() -> None:
    op.drop_column("album", "chapters")
