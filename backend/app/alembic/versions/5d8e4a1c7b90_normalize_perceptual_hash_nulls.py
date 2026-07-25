"""normalize perceptual hash nulls

Revision ID: 5d8e4a1c7b90
Revises: 3a6e5f8b1c2d
Create Date: 2026-07-24 18:45:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "5d8e4a1c7b90"
down_revision = "3a6e5f8b1c2d"
branch_labels = None
depends_on = None


def _normalize_json_null(table_name: str) -> None:
    table = sa.table(table_name, sa.column("perceptual_hashes", sa.JSON()))
    op.get_bind().execute(
        sa.update(table)
        .where(sa.cast(table.c.perceptual_hashes, sa.Text) == "null")
        .values(perceptual_hashes=sa.null())
    )


def upgrade() -> None:
    _normalize_json_null("album_media")
    _normalize_json_null("album_media_undo_snapshot")


def downgrade() -> None:
    pass
