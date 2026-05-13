from datetime import UTC, datetime
from importlib import import_module
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import create_engine

if TYPE_CHECKING:
    import pytest

external_media_schema = import_module(
    "app.alembic.versions.9f7c8a4d1b2e_external_media_schema"
)


def _legacy_tables(metadata: sa.MetaData) -> tuple[sa.Table, sa.Table]:
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
    return user, album


def _new_tables(metadata: sa.MetaData) -> tuple[sa.Table, sa.Table]:
    source_ref = sa.Table(
        "album_media_source_ref",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("uid", sa.Integer, nullable=False),
        sa.Column("aid", sa.String, nullable=False),
        sa.Column("source_kind", sa.String, nullable=False),
        sa.Column("google_media_id", sa.String),
        sa.Column("mime_type", sa.String),
        sa.Column("width", sa.Integer),
        sa.Column("height", sa.Integer),
        sa.Column("captured_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    media = sa.Table(
        "album_media",
        metadata,
        sa.Column("uid", sa.Integer, primary_key=True),
        sa.Column("aid", sa.String, primary_key=True),
        sa.Column("name", sa.String, primary_key=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("storage_path", sa.String, nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("byte_size", sa.BigInteger, nullable=False),
        sa.Column("source_ref_id", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    return source_ref, media


def test_upgrade_copies_album_media_and_google_upgrade_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    metadata = sa.MetaData()
    user, album = _legacy_tables(metadata)
    source_ref, media = _new_tables(metadata)
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
        refs = conn.execute(sa.select(source_ref)).mappings().all()

    assert [
        (row["name"], row["kind"], row["width"], row["height"]) for row in media_rows
    ] == [
        ("clip.mp4", "video", 1920, 1080),
        ("photo.jpg", "photo", 1200, 800),
    ]
    assert refs[0]["google_media_id"] == "google-1"
    photo_row = next(row for row in media_rows if row["name"] == "photo.jpg")
    assert photo_row["source_ref_id"] == refs[0]["id"]


def test_downgrade_rebuilds_album_json_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    metadata = sa.MetaData()
    user, album = _legacy_tables(metadata)
    source_ref, media = _new_tables(metadata)
    metadata.create_all(engine)
    now = datetime.now(UTC)

    with engine.begin() as conn:
        conn.execute(user.insert().values(id=1))
        conn.execute(
            album.insert().values(uid=1, id="aid-1", media=[], upgraded_media={})
        )
        ref_id = conn.execute(
            source_ref.insert()
            .values(
                uid=1,
                aid="aid-1",
                source_kind="google_photos",
                google_media_id="google-1",
                created_at=now,
            )
            .returning(source_ref.c.id)
        ).scalar_one()
        conn.execute(
            media.insert(),
            [
                {
                    "uid": 1,
                    "aid": "aid-1",
                    "name": "photo.jpg",
                    "kind": "photo",
                    "storage_path": "photo.jpg",
                    "width": 1200,
                    "height": 800,
                    "byte_size": 0,
                    "source_ref_id": ref_id,
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )
        monkeypatch.setattr(external_media_schema.op, "get_bind", lambda: conn)

        external_media_schema._migrate_media_rows_to_album_json()

        migrated = conn.execute(sa.select(album)).mappings().one()

    assert migrated["media"] == [{"name": "photo.jpg", "width": 1200, "height": 800}]
    assert migrated["upgraded_media"] == {"photo.jpg": "google-1"}
