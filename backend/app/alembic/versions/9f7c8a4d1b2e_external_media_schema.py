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
album_media_source_ref = sa.table(
    "album_media_source_ref",
    sa.column("id", sa.Integer()),
    sa.column("uid", sa.Integer()),
    sa.column("aid", sqlmodel.sql.sqltypes.AutoString()),
    sa.column("source_kind", sa.String(32)),
    sa.column("google_media_id", sqlmodel.sql.sqltypes.AutoString(length=256)),
    sa.column("mime_type", sqlmodel.sql.sqltypes.AutoString(length=255)),
    sa.column("width", sa.Integer()),
    sa.column("height", sa.Integer()),
    sa.column("captured_at", sa.DateTime(timezone=True)),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
album_media = sa.table(
    "album_media",
    sa.column("uid", sa.Integer()),
    sa.column("aid", sqlmodel.sql.sqltypes.AutoString()),
    sa.column("name", sqlmodel.sql.sqltypes.AutoString(length=255)),
    sa.column("kind", sa.String(16)),
    sa.column("storage_path", sqlmodel.sql.sqltypes.AutoString(length=255)),
    sa.column("width", sa.Integer()),
    sa.column("height", sa.Integer()),
    sa.column("byte_size", sa.BigInteger()),
    sa.column("source_ref_id", sa.Integer()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
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


def _upgraded_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(name): str(google_id)
        for name, google_id in value.items()
        if name and google_id
    }


def _insert_source_ref(
    connection: sa.Connection,
    *,
    uid: int,
    aid: str,
    google_media_id: str,
    created_at: datetime,
) -> int | None:
    result = connection.execute(
        album_media_source_ref.insert()
        .values(
            uid=uid,
            aid=aid,
            source_kind="google_photos",
            google_media_id=google_media_id,
            mime_type=None,
            width=None,
            height=None,
            captured_at=None,
            created_at=created_at,
        )
        .returning(album_media_source_ref.c.id)
    )
    return result.scalar_one_or_none()


def _migrate_album_json_to_media_rows() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    for row in connection.execute(
        sa.select(album.c.uid, album.c.id, album.c.media, album.c.upgraded_media)
    ).mappings():
        upgraded = _upgraded_map(row["upgraded_media"])
        source_ids = {
            name: _insert_source_ref(
                connection,
                uid=row["uid"],
                aid=row["id"],
                google_media_id=google_id,
                created_at=now,
            )
            for name, google_id in upgraded.items()
        }
        media_rows = [
            {
                "uid": row["uid"],
                "aid": row["id"],
                "name": item["name"],
                "kind": "video" if str(item["name"]).endswith(".mp4") else "photo",
                "storage_path": item["name"],
                "width": item.get("width", 0),
                "height": item.get("height", 0),
                "byte_size": 0,
                "source_ref_id": source_ids.get(str(item["name"])),
                "created_at": now,
                "updated_at": now,
            }
            for item in _media_rows(row["media"])
        ]
        if media_rows:
            connection.execute(album_media.insert(), media_rows)


def _migrate_media_rows_to_album_json() -> None:
    connection = op.get_bind()
    media_by_album: dict[tuple[int, str], list[dict[str, object]]] = {}
    upgraded_by_album: dict[tuple[int, str], dict[str, str]] = {}
    ref_rows = {
        ref["id"]: ref
        for ref in connection.execute(sa.select(album_media_source_ref)).mappings()
    }
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
        ref = ref_rows.get(row["source_ref_id"])
        if ref and ref["source_kind"] == "google_photos" and ref["google_media_id"]:
            upgraded_by_album.setdefault(key, {})[row["name"]] = ref["google_media_id"]

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


def upgrade() -> None:
    op.create_table(
        "album_media_source_ref",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "google_media_id",
            sqlmodel.sql.sqltypes.AutoString(length=256),
            nullable=True,
        ),
        sa.Column(
            "mime_type",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uid", "aid"], ["album.uid", "album.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uid"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "album_media",
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("aid", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "storage_path",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uid", "aid"], ["album.uid", "album.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_ref_id"], ["album_media_source_ref.id"]),
        sa.ForeignKeyConstraint(["uid"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("uid", "aid", "name"),
        sa.UniqueConstraint("uid", "aid", "name", name="uq_album_media_name"),
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
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_ref_id"], ["album_media_source_ref.id"]),
        sa.ForeignKeyConstraint(
            ["uid", "aid", "media_name"],
            ["album_media.uid", "album_media.aid", "album_media.name"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("uid", "aid", "media_name"),
    )
    _migrate_album_json_to_media_rows()
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
    _migrate_media_rows_to_album_json()
    op.drop_table("album_media_undo_snapshot")
    op.drop_table("album_media")
    op.drop_table("album_media_source_ref")
