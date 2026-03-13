"""add orientations to step

Revision ID: 24f88e631006
Revises: 8ec97bc11b0c
Create Date: 2026-03-13 21:41:13.979695

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '24f88e631006'
down_revision = '8ec97bc11b0c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'step',
        sa.Column('orientations', sa.JSON(), nullable=False, server_default='{}'),
    )


def downgrade():
    op.drop_column('step', 'orientations')
