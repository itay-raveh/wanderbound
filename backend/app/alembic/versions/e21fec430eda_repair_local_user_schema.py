"""Repair local user schema.

Revision ID: e21fec430eda
Revises: e4f6a8b0c2d3
Create Date: 2026-07-27 22:10:00.000000
"""

from alembic import op

revision = "e21fec430eda"
down_revision = "e4f6a8b0c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE "user" DROP CONSTRAINT IF EXISTS ck_user_has_identity')
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS is_local')


def downgrade() -> None:
    pass
