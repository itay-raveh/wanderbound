"""Replace the temporary chunk session with direct multipart state."""

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision = "7c2a9f4d8e10"
down_revision = "3a1b9d7f6c20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("upload_session")
    op.create_table(
        "upload_session",
        sa.Column("upload_id", sqlmodel.sql.sqltypes.AutoString(255), primary_key=True),
        sa.Column("owner", sqlmodel.sql.sqltypes.AutoString(255), nullable=False),
        sa.Column("object_key", sqlmodel.sql.sqltypes.AutoString(500), nullable=False),
        sa.Column("provider_upload_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sqlmodel.sql.sqltypes.AutoString(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(20), nullable=False),
        sa.Column("error_code", sqlmodel.sql.sqltypes.AutoString(100), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_upload_session_object_key", "upload_session", ["object_key"], unique=True
    )
    op.create_index(
        "ix_upload_session_owner_status",
        "upload_session",
        ["owner", "status"],
    )
    op.create_index(
        "ix_upload_session_expires_at", "upload_session", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("upload_session")
    op.create_table(
        "upload_session",
        sa.Column("upload_id", sqlmodel.sql.sqltypes.AutoString(255), primary_key=True),
        sa.Column("owner", sqlmodel.sql.sqltypes.AutoString(255), nullable=False),
        sa.Column("max_bytes", sa.BigInteger(), nullable=False),
        sa.Column("max_chunks", sa.Integer(), nullable=False),
        sa.Column("accumulated_bytes", sa.BigInteger(), nullable=False),
        sa.Column("chunks_written", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_upload_session_expires_at",
        "upload_session",
        ["expires_at"],
    )
    op.create_index("ix_upload_session_owner", "upload_session", ["owner"])
