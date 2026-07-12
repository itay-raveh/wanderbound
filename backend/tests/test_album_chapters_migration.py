from importlib import import_module
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import create_engine

if TYPE_CHECKING:
    import pytest

album_chapters = import_module("app.alembic.versions.3a1b9d7f6c20_add_album_chapters")


def _legacy_tables(metadata: sa.MetaData) -> tuple[sa.Table, sa.Table, sa.Table]:
    user = sa.Table("user", metadata, sa.Column("id", sa.Integer, primary_key=True))
    album = sa.Table(
        "album",
        metadata,
        sa.Column("uid", sa.Integer, sa.ForeignKey("user.id"), primary_key=True),
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("subtitle", sa.String(255), nullable=False),
        sa.Column("front_cover_photo", sa.String(255), nullable=False),
        sa.Column("back_cover_photo", sa.String(255), nullable=False),
        sa.Column("chapters", sa.JSON, nullable=False, server_default="[]"),
    )
    step = sa.Table(
        "step",
        metadata,
        sa.Column("uid", sa.Integer, primary_key=True),
        sa.Column("aid", sa.String, primary_key=True),
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("timestamp", sa.Float, nullable=False),
    )
    return user, album, step


def test_upgrade_copies_existing_album_data_into_default_chapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    metadata = sa.MetaData()
    user, album, step = _legacy_tables(metadata)
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(user.insert().values(id=1))
        conn.execute(
            album.insert().values(
                uid=1,
                id="trip-1",
                title="South America",
                subtitle="2024-2025",
                front_cover_photo="front.jpg",
                back_cover_photo="back.jpg",
                chapters=[],
            )
        )
        conn.execute(
            step.insert(),
            [
                {"uid": 1, "aid": "trip-1", "id": 20, "timestamp": 200.0},
                {"uid": 1, "aid": "trip-1", "id": 10, "timestamp": 100.0},
                {"uid": 1, "aid": "trip-1", "id": 30, "timestamp": 200.0},
            ],
        )
        monkeypatch.setattr(album_chapters.op, "get_bind", lambda: conn)

        album_chapters._migrate_album_fields_to_default_chapters()

        migrated = conn.execute(sa.select(album)).mappings().one()

    assert migrated["chapters"] == [
        {
            "id": "chapter-1",
            "title": "South America",
            "subtitle": "2024-2025",
            "step_ids": [10, 20, 30],
            "front_cover_photo": "front.jpg",
            "back_cover_photo": "back.jpg",
        }
    ]


def test_downgrade_restores_album_fields_from_first_chapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    metadata = sa.MetaData()
    user, album, _step = _legacy_tables(metadata)
    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(user.insert().values(id=1))
        conn.execute(
            album.insert().values(
                uid=1,
                id="trip-1",
                title="",
                subtitle="",
                front_cover_photo="",
                back_cover_photo="",
                chapters=[
                    {
                        "id": "chapter-1",
                        "title": "Restored Title",
                        "subtitle": "Restored Subtitle",
                        "step_ids": [1],
                        "front_cover_photo": "front.jpg",
                        "back_cover_photo": "back.jpg",
                    }
                ],
            )
        )
        monkeypatch.setattr(album_chapters.op, "get_bind", lambda: conn)

        album_chapters._migrate_default_chapters_to_album_fields()

        restored = conn.execute(sa.select(album)).mappings().one()

    assert restored["title"] == "Restored Title"
    assert restored["subtitle"] == "Restored Subtitle"
    assert restored["front_cover_photo"] == "front.jpg"
    assert restored["back_cover_photo"] == "back.jpg"
