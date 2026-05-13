"""external media schema

Revision ID: 9f7c8a4d1b2e
Revises: dcb0d4e8f8b3
Create Date: 2026-05-13 12:00:00.000000

"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "9f7c8a4d1b2e"
down_revision = "dcb0d4e8f8b3"
branch_labels = None
depends_on = None


album = sa.table(
    "album",
    sa.column("uid", sa.Integer()),
    sa.column("id", sqlmodel.sql.sqltypes.AutoString()),
    sa.column("media", sa.JSON()),
    sa.column("upgraded_media", sa.JSON()),
)
step = sa.table(
    "step",
    sa.column("uid", sa.Integer()),
    sa.column("aid", sqlmodel.sql.sqltypes.AutoString()),
    sa.column("id", sa.Integer()),
    sa.column("cover", sqlmodel.sql.sqltypes.AutoString(length=255)),
    sa.column("cover_media_name", sqlmodel.sql.sqltypes.AutoString(length=255)),
    sa.column("pages", sa.JSON()),
    sa.column("unused", sa.JSON()),
)
album_media = sa.table(
    "album_media",
    sa.column("uid", sa.Integer()),
    sa.column("aid", sqlmodel.sql.sqltypes.AutoString()),
    sa.column("name", sqlmodel.sql.sqltypes.AutoString(length=255)),
    sa.column("kind", sa.String(16)),
    sa.column("width", sa.Integer()),
    sa.column("height", sa.Integer()),
    sa.column("byte_size", sa.BigInteger()),
    sa.column("upgrade_candidate", sa.Boolean()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
step_page_media = sa.table(
    "step_page_media",
    sa.column("uid", sa.Integer()),
    sa.column("aid", sqlmodel.sql.sqltypes.AutoString()),
    sa.column("step_id", sa.Integer()),
    sa.column("page_index", sa.Integer()),
    sa.column("position_index", sa.Integer()),
    sa.column("media_name", sqlmodel.sql.sqltypes.AutoString(length=255)),
)
step_unused_media = sa.table(
    "step_unused_media",
    sa.column("uid", sa.Integer()),
    sa.column("aid", sqlmodel.sql.sqltypes.AutoString()),
    sa.column("step_id", sa.Integer()),
    sa.column("position_index", sa.Integer()),
    sa.column("media_name", sqlmodel.sql.sqltypes.AutoString(length=255)),
)


def _media_rows(media_value: object) -> list[dict[str, object]]:
    if not isinstance(media_value, list):
        return []
    rows: list[dict[str, object]] = []
    for item in media_value:
        if not isinstance(item, Mapping):
            continue
        item = cast("Mapping[str, object]", item)
        name = item.get("name")
        if not name:
            continue
        rows.append(
            {
                "name": str(name),
                "width": item.get("width", 0),
                "height": item.get("height", 0),
            }
        )
    return rows


def _upgraded_names(value: object) -> set[str]:
    if not isinstance(value, dict):
        return set()
    return {str(name) for name, google_id in value.items() if name and google_id}


def _list_of_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _pages(value: object) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    return [_list_of_strings(page) for page in value]


def _migrate_album_json_to_media_rows() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    for row in connection.execute(
        sa.select(album.c.uid, album.c.id, album.c.media, album.c.upgraded_media)
    ).mappings():
        upgraded = _upgraded_names(row["upgraded_media"])
        media_rows = [
            {
                "uid": row["uid"],
                "aid": row["id"],
                "name": item["name"],
                "kind": "video" if str(item["name"]).endswith(".mp4") else "photo",
                "width": item.get("width", 0),
                "height": item.get("height", 0),
                "byte_size": 0,
                "upgrade_candidate": str(item["name"]) not in upgraded,
                "created_at": now,
                "updated_at": now,
            }
            for item in _media_rows(row["media"])
        ]
        if media_rows:
            connection.execute(album_media.insert(), media_rows)


def _migrate_step_json_to_media_rows() -> None:
    connection = op.get_bind()
    page_rows: list[dict[str, object]] = []
    unused_rows: list[dict[str, object]] = []
    for row in connection.execute(
        sa.select(
            step.c.uid,
            step.c.aid,
            step.c.id,
            step.c.cover,
            step.c.pages,
            step.c.unused,
        )
    ).mappings():
        connection.execute(
            step.update()
            .where(
                step.c.uid == row["uid"],
                step.c.aid == row["aid"],
                step.c.id == row["id"],
            )
            .values(cover_media_name=row["cover"])
        )
        for page_index, page in enumerate(_pages(row["pages"])):
            for position_index, media_name in enumerate(page):
                page_rows.append(
                    {
                        "uid": row["uid"],
                        "aid": row["aid"],
                        "step_id": row["id"],
                        "page_index": page_index,
                        "position_index": position_index,
                        "media_name": media_name,
                    }
                )
        for position_index, media_name in enumerate(_list_of_strings(row["unused"])):
            unused_rows.append(
                {
                    "uid": row["uid"],
                    "aid": row["aid"],
                    "step_id": row["id"],
                    "position_index": position_index,
                    "media_name": media_name,
                }
            )
    if page_rows:
        connection.execute(step_page_media.insert(), page_rows)
    if unused_rows:
        connection.execute(step_unused_media.insert(), unused_rows)


def _migrate_media_rows_to_album_json() -> None:
    connection = op.get_bind()
    media_by_album: dict[tuple[int, str], list[dict[str, object]]] = {}
    upgraded_by_album: dict[tuple[int, str], dict[str, str]] = {}
    for row in connection.execute(
        sa.select(album_media).order_by(album_media.c.created_at, album_media.c.name)
    ).mappings():
        key = (row["uid"], row["aid"])
        media_by_album.setdefault(key, []).append(
            {
                "name": row["name"],
                "width": row["width"],
                "height": row["height"],
            }
        )
        if not row["upgrade_candidate"]:
            upgraded_by_album.setdefault(key, {})[row["name"]] = "upgraded"

    for row in connection.execute(sa.select(album.c.uid, album.c.id)).mappings():
        key = (row["uid"], row["id"])
        connection.execute(
            album.update()
            .where(album.c.uid == row["uid"], album.c.id == row["id"])
            .values(
                media=media_by_album.get(key, []),
                upgraded_media=upgraded_by_album.get(key, {}),
            )
        )


def _migrate_step_media_rows_to_json() -> None:
    connection = op.get_bind()
    pages_by_step: dict[tuple[int, str, int], list[list[str]]] = {}
    for row in connection.execute(
        sa.select(step_page_media).order_by(
            step_page_media.c.page_index,
            step_page_media.c.position_index,
        )
    ).mappings():
        key = (row["uid"], row["aid"], row["step_id"])
        pages = pages_by_step.setdefault(key, [])
        while len(pages) <= row["page_index"]:
            pages.append([])
        pages[row["page_index"]].append(row["media_name"])

    unused_by_step: dict[tuple[int, str, int], list[str]] = {}
    for row in connection.execute(
        sa.select(step_unused_media).order_by(step_unused_media.c.position_index)
    ).mappings():
        key = (row["uid"], row["aid"], row["step_id"])
        unused_by_step.setdefault(key, []).append(row["media_name"])

    for row in connection.execute(sa.select(step)).mappings():
        key = (row["uid"], row["aid"], row["id"])
        connection.execute(
            step.update()
            .where(
                step.c.uid == row["uid"],
                step.c.aid == row["aid"],
                step.c.id == row["id"],
            )
            .values(
                cover=row["cover_media_name"],
                pages=pages_by_step.get(key, []),
                unused=unused_by_step.get(key, []),
            )
        )


def upgrade() -> None:
    op.create_table(
        "album_media",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("upgrade_candidate", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["uid", "aid"], ["album.uid", "album.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["uid"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uid", "aid", "name"),
    )
    op.add_column(
        "step",
        sa.Column(
            "cover_media_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_step_cover_album_media",
        "step",
        "album_media",
        ["uid", "aid", "cover_media_name"],
        ["uid", "aid", "name"],
    )
    op.create_table(
        "step_page_media",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("position_index", sa.Integer(), nullable=False),
        sa.Column(
            "media_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "media_name"],
            ["album_media.uid", "album_media.aid", "album_media.name"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "step_id"],
            ["step.uid", "step.aid", "step.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uid", "aid", "step_id", "page_index", "position_index"),
    )
    op.create_table(
        "step_unused_media",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("position_index", sa.Integer(), nullable=False),
        sa.Column(
            "media_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "media_name"],
            ["album_media.uid", "album_media.aid", "album_media.name"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "step_id"],
            ["step.uid", "step.aid", "step.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uid", "aid", "step_id", "position_index"),
    )
    op.create_table(
        "album_media_undo_snapshot",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "media_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "snapshot_path",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("upgrade_candidate", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "media_name"],
            ["album_media.uid", "album_media.aid", "album_media.name"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uid", "aid", "media_name"),
    )
    _migrate_album_json_to_media_rows()
    _migrate_step_json_to_media_rows()
    op.drop_column("step", "unused")
    op.drop_column("step", "pages")
    op.drop_column("step", "cover")
    op.drop_column("album", "upgraded_media")
    op.drop_column("album", "media")


def downgrade() -> None:
    op.add_column(
        "album",
        sa.Column("media", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "album",
        sa.Column("upgraded_media", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column("step", sa.Column("cover", sqlmodel.sql.sqltypes.AutoString()))
    op.add_column(
        "step", sa.Column("pages", sa.JSON(), nullable=False, server_default="[]")
    )
    op.add_column(
        "step", sa.Column("unused", sa.JSON(), nullable=False, server_default="[]")
    )
    _migrate_media_rows_to_album_json()
    _migrate_step_media_rows_to_json()
    op.drop_table("album_media_undo_snapshot")
    op.drop_table("step_unused_media")
    op.drop_table("step_page_media")
    op.drop_constraint("fk_step_cover_album_media", "step", type_="foreignkey")
    op.drop_column("step", "cover_media_name")
    op.drop_table("album_media")
