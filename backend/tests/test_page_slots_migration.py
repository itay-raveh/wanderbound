from importlib import import_module
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

if TYPE_CHECKING:
    import pytest


migration = import_module("app.alembic.versions.8f61c23e0a95_add_stable_page_slots")


def test_upgrade_preserves_page_order_photos_and_orientation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table(
        "step",
        metadata,
        sa.Column("uid", sa.Integer, primary_key=True),
        sa.Column("aid", sa.String, primary_key=True),
        sa.Column("id", sa.Integer, primary_key=True),
    )
    media = sa.Table(
        "album_media",
        metadata,
        sa.Column("uid", sa.Integer, primary_key=True),
        sa.Column("aid", sa.String, primary_key=True),
        sa.Column("name", sa.String, primary_key=True),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
    )
    old = sa.Table(
        "step_page_media",
        metadata,
        sa.Column("uid", sa.Integer, primary_key=True),
        sa.Column("aid", sa.String, primary_key=True),
        sa.Column("step_id", sa.Integer, primary_key=True),
        sa.Column("page_index", sa.Integer, primary_key=True),
        sa.Column("position_index", sa.Integer, primary_key=True),
        sa.Column("page_kind", sa.String, nullable=False),
        sa.Column("media_name", sa.String, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            media.insert(),
            [
                {
                    "uid": 1,
                    "aid": "trip",
                    "name": "a.jpg",
                    "width": 800,
                    "height": 1200,
                },
                {
                    "uid": 1,
                    "aid": "trip",
                    "name": "b.jpg",
                    "width": 1200,
                    "height": 800,
                },
            ],
        )
        conn.execute(
            old.insert(),
            [
                {
                    "uid": 1,
                    "aid": "trip",
                    "step_id": 4,
                    "page_index": 2,
                    "position_index": 0,
                    "page_kind": "grid",
                    "media_name": "b.jpg",
                },
                {
                    "uid": 1,
                    "aid": "trip",
                    "step_id": 4,
                    "page_index": 0,
                    "position_index": 0,
                    "page_kind": "grid",
                    "media_name": "a.jpg",
                },
            ],
        )
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(conn))
        )
        migration.upgrade()
        rows = (
            conn.execute(
                sa.text(
                    "SELECT p.id AS page_id, p.position_index, s.id AS slot_id, "
                    "s.media_name, s.frame_orientation FROM step_page p "
                    "JOIN step_page_slot s ON s.page_id = p.id "
                    "ORDER BY p.position_index"
                )
            )
            .mappings()
            .all()
        )

    assert [
        (r["position_index"], r["media_name"], r["frame_orientation"]) for r in rows
    ] == [(0, "a.jpg", "portrait"), (2, "b.jpg", "landscape")]
    assert len({r["page_id"] for r in rows}) == 2
    assert len({r["slot_id"] for r in rows}) == 2
