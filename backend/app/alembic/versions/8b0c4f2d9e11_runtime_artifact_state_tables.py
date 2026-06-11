# ruff: noqa: INP001
"""Runtime artifact state tables.

Revision ID: 8b0c4f2d9e11
Revises: 4d9e8a71c2b3
Create Date: 2026-06-10 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "8b0c4f2d9e11"
down_revision = "4d9e8a71c2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "upload_session",
        sa.Column("upload_id", sa.String(length=255), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("max_bytes", sa.Integer(), nullable=False),
        sa.Column("max_chunks", sa.Integer(), nullable=False),
        sa.Column("accumulated_bytes", sa.Integer(), nullable=False),
        sa.Column("chunks_written", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("upload_id"),
    )
    op.create_index(
        "ix_upload_session_expires_at",
        "upload_session",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_upload_session_owner",
        "upload_session",
        ["owner"],
        unique=False,
    )

    op.create_table(
        "artifact_token",
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("namespace", sa.String(length=100), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token"),
    )
    op.create_index(
        "ix_artifact_token_expires_at",
        "artifact_token",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_artifact_token_namespace",
        "artifact_token",
        ["namespace"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_artifact_token_namespace", table_name="artifact_token")
    op.drop_index("ix_artifact_token_expires_at", table_name="artifact_token")
    op.drop_table("artifact_token")

    op.drop_index("ix_upload_session_owner", table_name="upload_session")
    op.drop_index("ix_upload_session_expires_at", table_name="upload_session")
    op.drop_table("upload_session")
