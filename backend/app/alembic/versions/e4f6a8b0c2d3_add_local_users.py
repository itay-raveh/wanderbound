"""Add local users.

Revision ID: e4f6a8b0c2d3
Revises: d3e5f7a9b1c2
Create Date: 2026-07-27 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "e4f6a8b0c2d3"
down_revision = "d3e5f7a9b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("is_local", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.drop_constraint("ck_user_has_provider", "user", type_="check")
    op.create_check_constraint(
        "ck_user_has_identity",
        "user",
        "is_demo OR is_local OR google_sub IS NOT NULL OR microsoft_sub IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_has_identity", "user", type_="check")
    op.create_check_constraint(
        "ck_user_has_provider",
        "user",
        "is_demo OR google_sub IS NOT NULL OR microsoft_sub IS NOT NULL",
    )
    op.drop_column("user", "is_local")
