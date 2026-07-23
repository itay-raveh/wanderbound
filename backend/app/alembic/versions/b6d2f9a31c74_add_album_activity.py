"""Add album activity timestamps."""

import sqlalchemy as sa
from alembic import op

revision = "b6d2f9a31c74"
down_revision = "a4e1c7b29d53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "album",
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_column("album", "last_active_at")
