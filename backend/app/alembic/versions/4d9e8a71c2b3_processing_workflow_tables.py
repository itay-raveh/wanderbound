# ruff: noqa: INP001
"""Processing workflow tables.

Revision ID: 4d9e8a71c2b3
Revises: 9f7c8a4d1b2e
Create Date: 2026-05-22 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "4d9e8a71c2b3"
down_revision = "9f7c8a4d1b2e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_operation",
        sa.Column("operation_id", sa.String(), nullable=False),
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("upload_generation", sa.Integer(), nullable=False),
        sa.Column("workflow_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_by_executor_id", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uid"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("operation_id"),
    )
    op.create_index(
        "ix_processing_operation_status",
        "processing_operation",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_processing_operation_uid",
        "processing_operation",
        ["uid"],
        unique=False,
    )
    op.create_index(
        "ix_processing_operation_uid_generation_created",
        "processing_operation",
        ["uid", "upload_generation", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_processing_operation_upload_generation",
        "processing_operation",
        ["upload_generation"],
        unique=False,
    )
    op.create_index(
        "ix_processing_operation_workflow_id",
        "processing_operation",
        ["workflow_id"],
        unique=True,
    )

    op.create_table(
        "processing_event",
        sa.Column("operation_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["processing_operation.operation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("operation_id", "seq"),
    )
    op.create_index(
        "ix_processing_event_event_type",
        "processing_event",
        ["event_type"],
        unique=False,
    )

    op.create_table(
        "workflow_executor_heartbeat",
        sa.Column("executor_id", sa.String(length=255), nullable=False),
        sa.Column("admin_base_url", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("executor_id"),
    )
    op.create_index(
        "ix_workflow_executor_heartbeat_last_seen_at",
        "workflow_executor_heartbeat",
        ["last_seen_at"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_executor_heartbeat_status",
        "workflow_executor_heartbeat",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workflow_executor_heartbeat_status",
        table_name="workflow_executor_heartbeat",
    )
    op.drop_index(
        "ix_workflow_executor_heartbeat_last_seen_at",
        table_name="workflow_executor_heartbeat",
    )
    op.drop_table("workflow_executor_heartbeat")

    op.drop_index("ix_processing_event_event_type", table_name="processing_event")
    op.drop_table("processing_event")

    op.drop_index(
        "ix_processing_operation_workflow_id",
        table_name="processing_operation",
    )
    op.drop_index(
        "ix_processing_operation_upload_generation",
        table_name="processing_operation",
    )
    op.drop_index(
        "ix_processing_operation_uid_generation_created",
        table_name="processing_operation",
    )
    op.drop_index("ix_processing_operation_uid", table_name="processing_operation")
    op.drop_index("ix_processing_operation_status", table_name="processing_operation")
    op.drop_table("processing_operation")
