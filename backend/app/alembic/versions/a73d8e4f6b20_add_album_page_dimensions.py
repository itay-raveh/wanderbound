"""Persist album page dimensions, preserving legacy A4 landscape albums."""

from alembic import op
import sqlalchemy as sa

revision = "a73d8e4f6b20"
down_revision = "c93e6b2d8a41"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("album", sa.Column("page_width_mm", sa.Float(), nullable=False, server_default="297"))
    op.add_column("album", sa.Column("page_height_mm", sa.Float(), nullable=False, server_default="210"))


def downgrade():
    op.drop_column("album", "page_height_mm")
    op.drop_column("album", "page_width_mm")
