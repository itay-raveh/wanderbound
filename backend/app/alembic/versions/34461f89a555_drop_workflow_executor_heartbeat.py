"""Drop workflow executor heartbeat.

Revision ID: 34461f89a555
Revises: e21fec430eda
Create Date: 2026-08-31 16:26:23.575314

"""

from alembic import op
import sqlalchemy as sa

revision = "34461f89a555"
down_revision = "e21fec430eda"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "ix_workflow_executor_heartbeat_last_seen_at",
        table_name="workflow_executor_heartbeat",
    )
    op.drop_index(
        "ix_workflow_executor_heartbeat_status",
        table_name="workflow_executor_heartbeat",
    )
    op.drop_table("workflow_executor_heartbeat")


def downgrade() -> None:
    op.create_table(
        "workflow_executor_heartbeat",
        sa.Column("executor_id", sa.String(length=255), nullable=False),
        sa.Column("admin_base_url", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("executor_id"),
    )
    op.create_index(
        "ix_workflow_executor_heartbeat_status",
        "workflow_executor_heartbeat",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_executor_heartbeat_last_seen_at",
        "workflow_executor_heartbeat",
        ["last_seen_at"],
        unique=False,
    )
