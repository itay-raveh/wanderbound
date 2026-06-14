# ruff: noqa: INP001
"""Widen upload session byte counts.

Revision ID: 1f6d2e8c9a0b
Revises: 8b0c4f2d9e11
Create Date: 2026-06-11 20:20:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "1f6d2e8c9a0b"
down_revision = "8b0c4f2d9e11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "upload_session",
        "max_bytes",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
    op.alter_column(
        "upload_session",
        "accumulated_bytes",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "upload_session",
        "accumulated_bytes",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "upload_session",
        "max_bytes",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
