"""Store non-destructive photo edits on album media.

Revision ID: 7e2c1a9b4d30
Revises: b45c61407294
"""

import sqlalchemy as sa
from alembic import op

revision = "7e2c1a9b4d30"
down_revision = "b45c61407294"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("album_media", sa.Column("photo_edit", sa.JSON(), nullable=True))
    op.add_column(
        "album_media_undo_snapshot", sa.Column("photo_edit", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("album_media_undo_snapshot", "photo_edit")
    op.drop_column("album_media", "photo_edit")
