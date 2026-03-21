"""storage_eviction

Revision ID: b3f1a2c8d9e0
Revises: 45e0a9ed4b74
Create Date: 2026-03-21 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b3f1a2c8d9e0"
down_revision = "45e0a9ed4b74"
branch_labels = None
depends_on = None


def upgrade():
    # Step: add id (Polarsteps step ID), migrate data from idx, replace PK
    op.add_column("step", sa.Column("id", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE step SET id = idx")
    op.drop_constraint("step_pkey", "step", type_="primary")
    op.create_primary_key("step_pkey", "step", ["uid", "aid", "id"])
    op.drop_column("step", "idx")

    # Album: rename orientations → media
    op.alter_column("album", "orientations", new_column_name="media")

    # User: add last_active_at
    op.add_column(
        "user",
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade():
    # User: drop last_active_at
    op.drop_column("user", "last_active_at")

    # Album: rename media → orientations
    op.alter_column("album", "media", new_column_name="orientations")

    # Step: restore idx from id
    op.add_column("step", sa.Column("idx", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE step SET idx = id")
    op.drop_constraint("step_pkey", "step", type_="primary")
    op.create_primary_key("step_pkey", "step", ["uid", "aid", "idx"])
    op.drop_column("step", "id")
