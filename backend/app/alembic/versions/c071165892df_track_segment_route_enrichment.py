"""Track segment route enrichment.

Revision ID: c071165892df
Revises: 34461f89a555
Create Date: 2026-08-31 17:54:58.821394

"""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c071165892df"
down_revision = "34461f89a555"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sa.Enum(
        "matched", "no_route", "failed", name="routeenrichmentstatus"
    ).create(op.get_bind())
    op.create_table(
        "segment_route_enrichment",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "matched",
                "no_route",
                "failed",
                name="routeenrichmentstatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "error_code",
            sqlmodel.sql.sqltypes.AutoString(length=100),
            nullable=True,
        ),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "start_time", "end_time"],
            [
                "segment.uid",
                "segment.aid",
                "segment.start_time",
                "segment.end_time",
            ],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uid", "aid", "start_time", "end_time"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO segment_route_enrichment (
                uid, aid, start_time, end_time, status, error_code, attempted_at
            )
            SELECT
                uid,
                aid,
                start_time,
                end_time,
                'matched'::routeenrichmentstatus,
                NULL,
                CURRENT_TIMESTAMP
            FROM segment
            WHERE route IS NOT NULL AND route::text <> 'null'
            """
        )
    )


def downgrade() -> None:
    op.drop_table("segment_route_enrichment")
    sa.Enum(
        "matched", "no_route", "failed", name="routeenrichmentstatus"
    ).drop(op.get_bind())
