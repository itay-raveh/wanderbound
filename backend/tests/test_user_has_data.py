"""Tests for User.has_data computed field and User.folder property."""

from pathlib import Path

import pytest

from app.core.config import get_settings
from app.models.user import User


@pytest.fixture
def user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> User:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    return User(
        id=42,
        google_sub="g-42",
        first_name="Test",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
        album_ids=[],
    )


class TestHasData:
    def test_false_when_folder_missing(self, user: User) -> None:
        assert not user.folder.exists()
        assert user.has_data is False

    def test_true_when_folder_exists(self, user: User) -> None:
        user.folder.mkdir(parents=True)
        assert user.has_data is True

    def test_true_with_files_inside(self, user: User) -> None:
        user.folder.mkdir(parents=True)
        (user.folder / "trip").mkdir()
        (user.folder / "trip" / "data.json").write_text("{}")
        assert user.has_data is True


class TestFolderProperty:
    def test_folder_path(self, user: User) -> None:
        assert user.folder.name == "42"
        assert user.folder.parent.name == "users"

    def test_trips_folder_path(self, user: User) -> None:
        assert user.trips_folder == user.folder / "trip"
