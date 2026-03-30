"""add route to segment

Revision ID: d4653fc8f2f2
Revises: f13331818c11
Create Date: 2026-03-30 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4653fc8f2f2'
down_revision = 'f13331818c11'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('segment', sa.Column('route', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('segment', 'route')
