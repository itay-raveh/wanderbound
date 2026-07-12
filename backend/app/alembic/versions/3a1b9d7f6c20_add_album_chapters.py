"""Move album content into chapters.

Revision ID: 3a1b9d7f6c20
Revises: 1f6d2e8c9a0b
Create Date: 2026-06-15 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from typing import cast

revision = "3a1b9d7f6c20"
down_revision = "1f6d2e8c9a0b"
branch_labels = None
depends_on = None

DEFAULT_CHAPTER_ID = "chapter-1"

album = sa.table(
    "album",
    sa.column("uid", sa.Integer()),
    sa.column("id", sa.String()),
    sa.column("title", sa.String(length=255)),
    sa.column("subtitle", sa.String(length=255)),
    sa.column("front_cover_photo", sa.String(length=255)),
    sa.column("back_cover_photo", sa.String(length=255)),
    sa.column("chapters", sa.JSON()),
)
step = sa.table(
    "step",
    sa.column("uid", sa.Integer()),
    sa.column("aid", sa.String()),
    sa.column("id", sa.Integer()),
    sa.column("timestamp", sa.Float()),
)


def _step_ids_for_album(
    connection: sa.Connection,
    uid: int,
    aid: str,
) -> list[int]:
    return list(
        connection.execute(
            sa.select(step.c.id)
            .where(step.c.uid == uid, step.c.aid == aid)
            .order_by(step.c.timestamp, step.c.id)
        ).scalars()
    )


def _migrate_album_fields_to_default_chapters() -> None:
    connection = op.get_bind()
    for row in connection.execute(
        sa.select(
            album.c.uid,
            album.c.id,
            album.c.title,
            album.c.subtitle,
            album.c.front_cover_photo,
            album.c.back_cover_photo,
        )
    ).mappings():
        connection.execute(
            album.update()
            .where(album.c.uid == row["uid"], album.c.id == row["id"])
            .values(
                chapters=[
                    {
                        "id": DEFAULT_CHAPTER_ID,
                        "title": row["title"],
                        "subtitle": row["subtitle"],
                        "step_ids": _step_ids_for_album(
                            connection,
                            row["uid"],
                            row["id"],
                        ),
                        "front_cover_photo": row["front_cover_photo"],
                        "back_cover_photo": row["back_cover_photo"],
                    }
                ]
            )
        )


def _first_chapter(value: object) -> dict[str, object]:
    if not isinstance(value, list) or not value or not isinstance(value[0], dict):
        return {}
    return cast("dict[str, object]", value[0])


def _migrate_default_chapters_to_album_fields() -> None:
    connection = op.get_bind()
    for row in connection.execute(
        sa.select(album.c.uid, album.c.id, album.c.chapters)
    ).mappings():
        chapter = _first_chapter(row["chapters"])
        connection.execute(
            album.update()
            .where(album.c.uid == row["uid"], album.c.id == row["id"])
            .values(
                title=chapter.get("title", ""),
                subtitle=chapter.get("subtitle", ""),
                front_cover_photo=chapter.get("front_cover_photo", ""),
                back_cover_photo=chapter.get("back_cover_photo", ""),
            )
        )


def upgrade() -> None:
    op.add_column(
        "album",
        sa.Column("chapters", sa.JSON(), nullable=False, server_default="[]"),
    )
    _migrate_album_fields_to_default_chapters()
    op.drop_column("album", "title")
    op.drop_column("album", "subtitle")
    op.drop_column("album", "front_cover_photo")
    op.drop_column("album", "back_cover_photo")


def downgrade() -> None:
    op.add_column("album", sa.Column("back_cover_photo", sa.String(255)))
    op.add_column("album", sa.Column("front_cover_photo", sa.String(255)))
    op.add_column("album", sa.Column("subtitle", sa.String(255)))
    op.add_column("album", sa.Column("title", sa.String(255)))
    _migrate_default_chapters_to_album_fields()
    op.drop_column("album", "chapters")
