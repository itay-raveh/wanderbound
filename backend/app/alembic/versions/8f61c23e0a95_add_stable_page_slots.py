"""Replace positional page media with stable pages and typed slots.

Revision ID: 8f61c23e0a95
Revises: 7e2c1a9b4d30
"""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "8f61c23e0a95"
down_revision = "7e2c1a9b4d30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "step_page",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sa.String(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("position_index", sa.Integer(), nullable=False),
        sa.Column("page_kind", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint("uid", "aid", "step_id", "id"),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "step_id"],
            ["step.uid", "step.aid", "step.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_step_page_order", "step_page", ["uid", "aid", "step_id", "position_index"]
    )
    op.create_table(
        "step_page_slot",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sa.String(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("page_id", sa.String(36), nullable=False),
        sa.Column("position_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("media_name", sa.String(255), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("frame_orientation", sa.String(16), nullable=False),
        sa.Column("continuation_priority", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("uid", "aid", "step_id", "id"),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "step_id", "page_id"],
            ["step_page.uid", "step_page.aid", "step_page.step_id", "step_page.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "media_name"],
            ["album_media.uid", "album_media.aid", "album_media.name"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "(kind = 'photo' AND media_name IS NOT NULL AND text_content IS NULL) "
            "OR (kind = 'text' AND media_name IS NULL AND text_content IS NOT NULL)",
            name="step_page_slot_content",
        ),
        sa.CheckConstraint(
            "frame_orientation IN ('portrait', 'landscape')",
            name="step_page_slot_orientation",
        ),
    )
    op.create_index(
        "ix_step_page_slot_order",
        "step_page_slot",
        ["uid", "aid", "step_id", "page_id", "position_index"],
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT old.uid, old.aid, old.step_id, old.page_index, "
            "old.position_index, old.page_kind, old.media_name, "
            "media.width, media.height "
            "FROM step_page_media AS old "
            "JOIN album_media AS media ON media.uid = old.uid "
            "AND media.aid = old.aid AND media.name = old.media_name "
            "ORDER BY old.uid, old.aid, old.step_id, old.page_index, "
            "old.position_index"
        )
    )
    page_ids: dict[tuple[int, str, int, int], str] = {}
    priorities: dict[tuple[int, str, int], int] = {}
    for row in rows.mappings():
        key = (row["uid"], row["aid"], row["step_id"], row["page_index"])
        page_id = page_ids.get(key)
        if page_id is None:
            page_id = str(uuid4())
            page_ids[key] = page_id
            connection.execute(
                sa.text(
                    "INSERT INTO step_page "
                    "(uid, aid, step_id, id, position_index, page_kind) "
                    "VALUES (:uid, :aid, :step_id, :id, :position_index, :page_kind)"
                ),
                {
                    "uid": row["uid"],
                    "aid": row["aid"],
                    "step_id": row["step_id"],
                    "id": page_id,
                    "position_index": row["page_index"],
                    "page_kind": row["page_kind"],
                },
            )
        connection.execute(
            sa.text(
                "INSERT INTO step_page_slot "
                "(uid, aid, step_id, id, page_id, position_index, kind, "
                "media_name, text_content, frame_orientation, continuation_priority) "
                "VALUES (:uid, :aid, :step_id, :id, :page_id, :position_index, "
                "'photo', :media_name, NULL, :frame_orientation, :continuation_priority)"
            ),
            {
                "uid": row["uid"],
                "aid": row["aid"],
                "step_id": row["step_id"],
                "id": str(uuid4()),
                "page_id": page_id,
                "position_index": row["position_index"],
                "media_name": row["media_name"],
                "frame_orientation": (
                    "portrait" if row["width"] / row["height"] < 9 / 10 else "landscape"
                ),
                "continuation_priority": priorities.get(key[:3], 0),
            },
        )
        priorities[key[:3]] = priorities.get(key[:3], 0) + 1
    op.drop_table("step_page_media")


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT 1 FROM step_page_slot WHERE kind = 'text' LIMIT 1")
    ).first():
        raise RuntimeError("Cannot downgrade while text slots exist")
    op.create_table(
        "step_page_media",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sa.String(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("position_index", sa.Integer(), nullable=False),
        sa.Column("media_name", sa.String(255), nullable=False),
        sa.Column("page_kind", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint(
            "uid", "aid", "step_id", "page_index", "position_index"
        ),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "step_id"],
            ["step.uid", "step.aid", "step.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "media_name"],
            ["album_media.uid", "album_media.aid", "album_media.name"],
            ondelete="CASCADE",
        ),
    )
    connection.execute(
        sa.text(
            "INSERT INTO step_page_media "
            "(uid, aid, step_id, page_index, position_index, media_name, page_kind) "
            "SELECT slot.uid, slot.aid, slot.step_id, page.position_index, "
            "slot.position_index, slot.media_name, page.page_kind "
            "FROM step_page_slot AS slot JOIN step_page AS page "
            "ON page.uid = slot.uid AND page.aid = slot.aid "
            "AND page.step_id = slot.step_id AND page.id = slot.page_id"
        )
    )
    op.drop_index("ix_step_page_slot_order", table_name="step_page_slot")
    op.drop_table("step_page_slot")
    op.drop_index("ix_step_page_order", table_name="step_page")
    op.drop_table("step_page")
