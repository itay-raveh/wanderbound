"""add print bleed dimensions

Revision ID: fffe0591309b
Revises: c071165892df
Create Date: 2026-09-10 14:04:27.397769

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fffe0591309b"
down_revision = "c071165892df"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "album",
        sa.Column("interior_bleed_mm", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "album",
        sa.Column("cover_bleed_mm", sa.Float(), server_default="0", nullable=False),
    )


def downgrade():
    op.drop_column("album", "cover_bleed_mm")
    op.drop_column("album", "interior_bleed_mm")
