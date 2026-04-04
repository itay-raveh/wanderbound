"""add is_demo to user

Revision ID: 086472e34c04
Revises: 27083dd2e4fd
Create Date: 2026-04-04 09:41:19.253211

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '086472e34c04'
down_revision = '27083dd2e4fd'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.drop_constraint('ck_user_has_provider', 'user', type_='check')
    op.create_check_constraint(
        'ck_user_has_provider', 'user',
        'is_demo OR google_sub IS NOT NULL OR microsoft_sub IS NOT NULL',
    )


def downgrade():
    op.drop_constraint('ck_user_has_provider', 'user', type_='check')
    op.create_check_constraint(
        'ck_user_has_provider', 'user',
        'google_sub IS NOT NULL OR microsoft_sub IS NOT NULL',
    )
    op.drop_column('user', 'is_demo')
