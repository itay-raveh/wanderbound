"""rename excluded_steps to hidden_steps, add hidden_headers

Revision ID: 6eee573c95c0
Revises: f097a964b67c
Create Date: 2026-04-03 20:14:49.556402

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '6eee573c95c0'
down_revision = 'f097a964b67c'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('album', 'excluded_steps', new_column_name='hidden_steps')
    op.add_column('album', sa.Column('hidden_headers', sa.JSON(), nullable=False, server_default='[]'))


def downgrade():
    op.drop_column('album', 'hidden_headers')
    op.alter_column('album', 'hidden_steps', new_column_name='excluded_steps')
