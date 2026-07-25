"""add explicit step pages

Revision ID: c2d4e6f8a0b1
Revises: b6d2f9a31c74
Create Date: 2026-07-26 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "c2d4e6f8a0b1"
down_revision = "b6d2f9a31c74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "step_page",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "step_id"],
            ["step.uid", "step.aid", "step.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uid", "aid", "step_id", "page_index"),
    )
    op.execute(
        """
        INSERT INTO step_page (uid, aid, step_id, page_index, kind)
        SELECT uid, aid, step_id, page_index, 'grid'
        FROM step_page_media
        GROUP BY uid, aid, step_id, page_index
        """
    )
    op.create_foreign_key(
        "fk_step_page_media_page",
        "step_page_media",
        "step_page",
        ["uid", "aid", "step_id", "page_index"],
        ["uid", "aid", "step_id", "page_index"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_step_page_media_page", "step_page_media", type_="foreignkey")
    op.drop_table("step_page")
