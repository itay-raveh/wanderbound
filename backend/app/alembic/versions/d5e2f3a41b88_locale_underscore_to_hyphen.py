"""locale_underscore_to_hyphen

Revision ID: d5e2f3a41b88
Revises: c4d9e1f23a77
Create Date: 2026-03-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd5e2f3a41b88'
down_revision = 'c4d9e1f23a77'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("UPDATE \"user\" SET locale = REPLACE(locale, '_', '-')"))


def downgrade():
    op.execute(sa.text("UPDATE \"user\" SET locale = REPLACE(locale, '-', '_')"))
