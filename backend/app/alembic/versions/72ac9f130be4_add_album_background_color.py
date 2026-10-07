"""Add optional album paper color; existing albums retain their theme default."""

import sqlalchemy as sa
from alembic import op

revision = "72ac9f130be4"
down_revision = "b45c61407294"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("album", sa.Column("background_color", sa.String(7), nullable=True))


def downgrade() -> None:
    op.drop_column("album", "background_color")
