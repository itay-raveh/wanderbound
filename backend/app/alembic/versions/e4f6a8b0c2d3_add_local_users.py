"""Add local users.

Revision ID: e4f6a8b0c2d3
Revises: d3e5f7a9b1c2
Create Date: 2026-07-27 00:00:00.000000
"""

from alembic import op

revision = "e4f6a8b0c2d3"
down_revision = "d3e5f7a9b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_user_has_provider", "user", type_="check")


def downgrade() -> None:
    op.create_check_constraint(
        "ck_user_has_provider",
        "user",
        "is_demo OR google_sub IS NOT NULL OR microsoft_sub IS NOT NULL",
    )
