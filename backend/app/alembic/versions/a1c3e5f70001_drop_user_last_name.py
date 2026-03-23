"""drop user last_name

Revision ID: a1c3e5f70001
Revises: b2121f6c7d00
Create Date: 2026-03-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c3e5f70001'
down_revision = 'b2121f6c7d00'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('user', 'last_name')


def downgrade() -> None:
    op.add_column('user', sa.Column('last_name', sa.String(length=255), nullable=False, server_default=''))
