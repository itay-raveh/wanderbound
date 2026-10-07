"""Merge album composition and background color migration branches.

Revision ID: c93e6b2d8a41
Revises: 8f61c23e0a95, 72ac9f130be4

Keep both existing histories so databases upgraded through either feature can
apply the other branch before converging on a single head.
"""

revision = "c93e6b2d8a41"
down_revision = ("8f61c23e0a95", "72ac9f130be4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
