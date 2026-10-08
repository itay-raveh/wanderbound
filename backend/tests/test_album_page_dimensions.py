from importlib import import_module
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError

from app.models.album import AlbumUpdate

if TYPE_CHECKING:
    from tests.helpers.albums import AlbumRoutes


@pytest.mark.usefixtures("signed_album")
async def test_page_dimensions_are_atomic_and_survive_other_partial_updates(
    album_routes: AlbumRoutes,
) -> None:
    saved = await album_routes.update_album_ok(
        page_width_mm=279.4, page_height_mm=215.9
    )
    assert (saved["page_width_mm"], saved["page_height_mm"]) == (279.4, 215.9)
    for payload in (
        {"page_width_mm": 355.6},
        {"page_width_mm": None, "page_height_mm": 210},
        {"page_width_mm": 420, "page_height_mm": 180},
        {"page_width_mm": 249, "page_height_mm": 200},
        {"page_width_mm": 300, "page_height_mm": 298},
    ):
        response = await album_routes.update_album(**payload, font="Rejected")
        assert response.status_code == 422
    updated = await album_routes.update_album_ok(show_page_numbers=True)
    assert (updated["page_width_mm"], updated["page_height_mm"]) == (279.4, 215.9)
    assert updated["font"] == saved["font"]


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_dimensions_are_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        AlbumUpdate.model_validate({"page_width_mm": value, "page_height_mm": 210})


def test_dimension_migration_preserves_legacy_album_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module(
        "app.alembic.versions.a73d8e4f6b20_add_album_page_dimensions"
    )
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE album (id TEXT PRIMARY KEY, chapters JSON NOT NULL, "
                "background_color TEXT)"
            )
        )
        conn.execute(
            sa.text("INSERT INTO album VALUES (:id, :chapters, :color)"),
            {"id": "old", "chapters": '[{"id":"chapter-1"}]', "color": "#112233"},
        )
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(conn))
        )
        migration.upgrade()
        row = conn.execute(sa.text("SELECT * FROM album")).mappings().one()
        assert dict(row) == {
            "id": "old",
            "chapters": '[{"id":"chapter-1"}]',
            "background_color": "#112233",
            "page_width_mm": 297,
            "page_height_mm": 210,
        }
        migration.downgrade()
        assert conn.execute(
            sa.text("SELECT id, chapters, background_color FROM album")
        ).one() == ("old", '[{"id":"chapter-1"}]', "#112233")
