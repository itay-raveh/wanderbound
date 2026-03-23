"""add microsoft_sub and make google_sub nullable

Revision ID: c3d4e5f60002
Revises: a1c3e5f70001
Create Date: 2026-03-23 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c3d4e5f60002"
down_revision = "a1c3e5f70001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("user", "google_sub", existing_type=sa.String(), nullable=True)
    op.add_column("user", sa.Column("microsoft_sub", sa.String(), nullable=True))
    op.create_index(
        op.f("ix_user_microsoft_sub"), "user", ["microsoft_sub"], unique=True
    )
    op.create_check_constraint(
        "ck_user_has_provider",
        "user",
        "google_sub IS NOT NULL OR microsoft_sub IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_has_provider", "user", type_="check")
    op.drop_index(op.f("ix_user_microsoft_sub"), table_name="user")
    op.drop_column("user", "microsoft_sub")
    op.alter_column("user", "google_sub", existing_type=sa.String(), nullable=False)
