from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import get_settings
from app.logic.eviction import _sizes_by_user, run_eviction
from app.models.user import User

from .conftest import make_async_session_mock

if TYPE_CHECKING:
    import pytest


def _make_file(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    return path


def _make_user(uid: int, *, hours_ago: int = 0) -> User:
    return User(
        id=uid,
        google_sub=f"g-{uid}",
        first_name="U",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
        album_ids=[],
        last_active_at=datetime.now(UTC) - timedelta(hours=hours_ago),
    )


class TestSizesByUser:
    def test_empty_dir(self, tmp_path: Path) -> None:
        total, by_user = _sizes_by_user(tmp_path)
        assert total == 0
        assert by_user == {}

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        total, by_user = _sizes_by_user(tmp_path / "nope")
        assert total == 0
        assert by_user == {}

    def test_sums_per_user(self, tmp_path: Path) -> None:
        _make_file(tmp_path / "1" / "a.txt", 100)
        _make_file(tmp_path / "2" / "b.txt", 200)
        total, by_user = _sizes_by_user(tmp_path)
        assert total == 300
        assert by_user == {1: 100, 2: 200}

    def test_includes_nested_files(self, tmp_path: Path) -> None:
        _make_file(tmp_path / "1" / "sub" / "deep.txt", 150)
        total, by_user = _sizes_by_user(tmp_path)
        assert total == 150
        assert by_user == {1: 150}


class TestRunEviction:
    async def test_noop_when_under_cap(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
        monkeypatch.setattr(get_settings(), "MAX_STORAGE_BYTES", 1000)

        users_folder = tmp_path / "users"
        _make_file(users_folder / "1" / "data.bin", 100)

        await run_eviction(skip_uid=999)

        assert (users_folder / "1" / "data.bin").exists()

    async def test_evicts_lru_user(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
        monkeypatch.setattr(get_settings(), "MAX_STORAGE_BYTES", 100)

        users_folder = tmp_path / "users"
        _make_file(users_folder / "1" / "data.bin", 80)
        _make_file(users_folder / "2" / "data.bin", 80)

        old_user = _make_user(1, hours_ago=48)
        recent_user = _make_user(2, hours_ago=1)

        mock_result = MagicMock()
        mock_result.all.return_value = [old_user, recent_user]
        mock_session = make_async_session_mock(exec=AsyncMock(return_value=mock_result))

        with patch("app.logic.eviction.AsyncSession", return_value=mock_session):
            await run_eviction(skip_uid=999)

        assert not (users_folder / "1").exists()
        assert (users_folder / "2" / "data.bin").exists()

    async def test_skips_uploading_user(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
        monkeypatch.setattr(get_settings(), "MAX_STORAGE_BYTES", 50)

        users_folder = tmp_path / "users"
        _make_file(users_folder / "1" / "data.bin", 80)
        _make_file(users_folder / "2" / "data.bin", 80)

        oldest_user = _make_user(1, hours_ago=100)
        other_user = _make_user(2, hours_ago=10)

        mock_result = MagicMock()
        mock_result.all.return_value = [oldest_user, other_user]
        mock_session = make_async_session_mock(exec=AsyncMock(return_value=mock_result))

        with patch("app.logic.eviction.AsyncSession", return_value=mock_session):
            await run_eviction(skip_uid=1)

        assert (users_folder / "1" / "data.bin").exists()
        assert not (users_folder / "2").exists()

    async def test_stops_when_under_cap(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
        monkeypatch.setattr(get_settings(), "MAX_STORAGE_BYTES", 120)

        users_folder = tmp_path / "users"
        _make_file(users_folder / "1" / "data.bin", 80)
        _make_file(users_folder / "2" / "data.bin", 80)
        _make_file(users_folder / "3" / "data.bin", 80)

        users = [
            _make_user(1, hours_ago=72),
            _make_user(2, hours_ago=48),
            _make_user(3, hours_ago=24),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = users
        mock_session = make_async_session_mock(exec=AsyncMock(return_value=mock_result))

        with patch("app.logic.eviction.AsyncSession", return_value=mock_session):
            await run_eviction(skip_uid=999)

        assert not (users_folder / "1").exists()
        assert not (users_folder / "2").exists()
        assert (users_folder / "3" / "data.bin").exists()

    async def test_skips_already_evicted_users(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
        monkeypatch.setattr(get_settings(), "MAX_STORAGE_BYTES", 50)

        users_folder = tmp_path / "users"
        # User 1 has no folder, user 2 has one
        _make_file(users_folder / "2" / "data.bin", 80)

        users = [
            _make_user(1, hours_ago=100),  # no folder on disk
            _make_user(2, hours_ago=10),
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = users
        mock_session = make_async_session_mock(exec=AsyncMock(return_value=mock_result))

        with patch("app.logic.eviction.AsyncSession", return_value=mock_session):
            await run_eviction(skip_uid=999)

        assert not (users_folder / "2").exists()
