"""rename upgraded_photos to upgraded_media

Revision ID: 5068e2946fb9
Revises: b119e3ee2c5b
Create Date: 2026-04-16 12:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '5068e2946fb9'
down_revision = 'b119e3ee2c5b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('album', 'upgraded_photos', new_column_name='upgraded_media')


def downgrade() -> None:
    op.alter_column('album', 'upgraded_media', new_column_name='upgraded_photos')
