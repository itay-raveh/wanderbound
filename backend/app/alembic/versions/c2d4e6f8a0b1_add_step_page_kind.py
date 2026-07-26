"""add step page kind

Revision ID: c2d4e6f8a0b1
Revises: b6d2f9a31c74
Create Date: 2026-07-26 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "c2d4e6f8a0b1"
down_revision = "b6d2f9a31c74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "step_page_media",
        sa.Column("page_kind", sa.String(length=16), nullable=False, server_default="grid"),
    )
    op.alter_column("step_page_media", "page_kind", server_default=None)


def downgrade() -> None:
    op.drop_column("step_page_media", "page_kind")
