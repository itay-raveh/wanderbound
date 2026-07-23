"""Add upload trip choices."""

import sqlalchemy as sa
from alembic import op

revision = "a4e1c7b29d53"
down_revision = "7c2a9f4d8e10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "upload_session",
        sa.Column(
            "trip_choices",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("upload_session", "trip_choices")
