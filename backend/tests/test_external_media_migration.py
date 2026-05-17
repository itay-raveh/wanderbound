from importlib import import_module
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import create_engine

if TYPE_CHECKING:
    import pytest

external_media_schema = import_module(
    "app.alembic.versions.9f7c8a4d1b2e_external_media_schema"
)


def _legacy_tables(metadata: sa.MetaData) -> tuple[sa.Table, sa.Table, sa.Table]:
    user = sa.Table(
        "user",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    album = sa.Table(
        "album",
        metadata,
        sa.Column("uid", sa.Integer, sa.ForeignKey("user.id"), primary_key=True),
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("media", sa.JSON, nullable=False),
        sa.Column("upgraded_media", sa.JSON, nullable=False),
    )
    step = sa.Table(
        "step",
        metadata,
        sa.Column("uid", sa.Integer, primary_key=True),
        sa.Column("aid", sa.String, primary_key=True),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cover", sa.String),
        sa.Column("cover_media_name", sa.String),
        sa.Column("pages", sa.JSON, nullable=False),
        sa.Column("unused", sa.JSON, nullable=False),
    )
    return user, album, step


def _new_tables(metadata: sa.MetaData) -> tuple[sa.Table, sa.Table, sa.Table]:
    media = sa.Table(
        "album_media",
        metadata,
        sa.Column("uid", sa.Integer, primary_key=True),
        sa.Column("aid", sa.String, primary_key=True),
        sa.Column("name", sa.String, primary_key=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("byte_size", sa.BigInteger, nullable=False),
        sa.Column("upgrade_candidate", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    page_media = sa.Table(
        "step_page_media",
        metadata,
        sa.Column("uid", sa.Integer, primary_key=True),
        sa.Column("aid", sa.String, primary_key=True),
        sa.Column("step_id", sa.Integer, primary_key=True),
        sa.Column("page_index", sa.Integer, primary_key=True),
        sa.Column("position_index", sa.Integer, primary_key=True),
        sa.Column("media_name", sa.String, nullable=False),
    )
    unused_media = sa.Table(
        "step_unused_media",
        metadata,
        sa.Column("uid", sa.Integer, primary_key=True),
        sa.Column("aid", sa.String, primary_key=True),
        sa.Column("step_id", sa.Integer, primary_key=True),
        sa.Column("position_index", sa.Integer, primary_key=True),
        sa.Column("media_name", sa.String, nullable=False),
    )
    return media, page_media, unused_media


def test_upgrade_copies_album_media_and_upgrade_candidate_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    metadata = sa.MetaData()
    user, album, _step = _legacy_tables(metadata)
    media, _page_media, _unused_media = _new_tables(metadata)
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(user.insert().values(id=1))
        conn.execute(
            album.insert().values(
                uid=1,
                id="aid-1",
                media=[
                    {"name": "photo.jpg", "width": 1200, "height": 800},
                    {"name": "clip.mp4", "width": 1920, "height": 1080},
                ],
                upgraded_media={"photo.jpg": "google-1"},
            )
        )
        monkeypatch.setattr(external_media_schema.op, "get_bind", lambda: conn)

        external_media_schema._migrate_album_json_to_media_rows()

        media_rows = (
            conn.execute(sa.select(media).order_by(media.c.name)).mappings().all()
        )

    assert [
        (
            row["name"],
            row["kind"],
            row["width"],
            row["height"],
            row["upgrade_candidate"],
        )
        for row in media_rows
    ] == [
        ("clip.mp4", "video", 1920, 1080, True),
        ("photo.jpg", "photo", 1200, 800, False),
    ]


def test_upgrade_copies_step_layout_to_relationship_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    metadata = sa.MetaData()
    user, album, step = _legacy_tables(metadata)
    _media, page_media, unused_media = _new_tables(metadata)
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(user.insert().values(id=1))
        conn.execute(
            album.insert().values(uid=1, id="aid-1", media=[], upgraded_media={})
        )
        conn.execute(
            step.insert().values(
                uid=1,
                aid="aid-1",
                id=7,
                cover="cover.jpg",
                pages=[["a.jpg", "b.jpg"], ["c.jpg"]],
                unused=["u.jpg"],
            )
        )
        monkeypatch.setattr(external_media_schema.op, "get_bind", lambda: conn)

        external_media_schema._migrate_step_json_to_media_rows()

        migrated_step = conn.execute(sa.select(step)).mappings().one()
        page_rows = (
            conn.execute(sa.select(page_media).order_by(page_media.c.media_name))
            .mappings()
            .all()
        )
        unused_rows = conn.execute(sa.select(unused_media)).mappings().all()

    assert migrated_step["cover_media_name"] == "cover.jpg"
    assert [
        (row["media_name"], row["page_index"], row["position_index"])
        for row in page_rows
    ] == [("a.jpg", 0, 0), ("b.jpg", 0, 1), ("c.jpg", 1, 0)]
    assert [(row["media_name"], row["position_index"]) for row in unused_rows] == [
        ("u.jpg", 0)
    ]
