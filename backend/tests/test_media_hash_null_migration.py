from importlib import import_module
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import create_engine

if TYPE_CHECKING:
    import pytest

media_hash_nulls = import_module(
    "app.alembic.versions.5d8e4a1c7b90_normalize_perceptual_hash_nulls"
)


def test_upgrade_converts_json_null_hashes_to_sql_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://")
    metadata = sa.MetaData()
    album_media = sa.Table(
        "album_media",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("perceptual_hashes", sa.JSON(none_as_null=False)),
    )
    undo_snapshot = sa.Table(
        "album_media_undo_snapshot",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("perceptual_hashes", sa.JSON(none_as_null=False)),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            album_media.insert(),
            [
                {"id": 1, "perceptual_hashes": None},
                {"id": 2, "perceptual_hashes": ["0123456789abcdef"]},
            ],
        )
        connection.execute(undo_snapshot.insert().values(id=1, perceptual_hashes=None))
        monkeypatch.setattr(media_hash_nulls.op, "get_bind", lambda: connection)

        media_hash_nulls.upgrade()

        media_rows = (
            connection.execute(sa.select(album_media).order_by(album_media.c.id))
            .mappings()
            .all()
        )
        undo_row = connection.execute(sa.select(undo_snapshot)).mappings().one()
        sql_null_count = connection.scalar(
            sa.select(sa.func.count())
            .select_from(album_media)
            .where(album_media.c.perceptual_hashes.is_(None))
        )

    assert sql_null_count == 1
    assert media_rows[0]["perceptual_hashes"] is None
    assert media_rows[1]["perceptual_hashes"] == ["0123456789abcdef"]
    assert undo_row["perceptual_hashes"] is None
