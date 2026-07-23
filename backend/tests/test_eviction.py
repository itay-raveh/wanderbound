from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import get_settings
from app.logic.eviction import _sizes_by_album, run_eviction
from app.models.album import Album

from .factories import make_album, make_async_session_mock

if TYPE_CHECKING:
    import pytest


def _make_file(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    return path


def _make_album(uid: int, aid: str, *, hours_ago: int = 0) -> Album:
    album = make_album(uid, aid)
    album.last_active_at = datetime.now(UTC) - timedelta(hours=hours_ago)
    return album


def _configure_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, max_bytes: int
) -> None:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    monkeypatch.setattr(get_settings(), "MAX_STORAGE_BYTES", max_bytes)


def _mock_eviction_albums(*albums: Album) -> patch:
    mock_result = MagicMock()
    mock_result.all.return_value = list(albums)
    mock_session = make_async_session_mock(exec=AsyncMock(return_value=mock_result))
    return patch("app.logic.eviction.AsyncSession", return_value=mock_session)


class TestSizesByAlbum:
    def test_sums_per_album(self, tmp_path: Path) -> None:
        _make_file(tmp_path / "1" / "trip" / "a" / "media.jpg", 100)
        _make_file(tmp_path / "1" / "trip" / "b" / "media.jpg", 200)
        total, by_album = _sizes_by_album(tmp_path)
        assert total == 300
        assert by_album == {(1, "a"): 100, (1, "b"): 200}

    def test_includes_nested_files(self, tmp_path: Path) -> None:
        _make_file(tmp_path / "1" / "trip" / "a" / "step" / "media.jpg", 150)
        total, by_album = _sizes_by_album(tmp_path)
        assert total == 150
        assert by_album == {(1, "a"): 150}


class TestRunEviction:
    async def test_noop_when_under_cap(
        self, tmp_path: Path, users_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_storage(tmp_path, monkeypatch, 1000)

        _make_file(users_dir / "1" / "trip" / "a" / "data.bin", 100)

        await run_eviction(skip_uid=999)

        assert (users_dir / "1" / "trip" / "a" / "data.bin").exists()

    async def test_evicts_lru_album_without_removing_its_user(
        self, tmp_path: Path, users_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_storage(tmp_path, monkeypatch, 100)

        _make_file(users_dir / "1" / "trip" / "old" / "data.bin", 80)
        _make_file(users_dir / "1" / "trip" / "recent" / "data.bin", 80)

        old_album = _make_album(1, "old", hours_ago=48)
        recent_album = _make_album(1, "recent", hours_ago=1)

        with _mock_eviction_albums(old_album, recent_album):
            await run_eviction(skip_uid=999)

        assert (users_dir / "1").exists()
        assert not (users_dir / "1" / "trip" / "old").exists()
        assert (users_dir / "1" / "trip" / "recent" / "data.bin").exists()

    async def test_skips_uploading_user(
        self, tmp_path: Path, users_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_storage(tmp_path, monkeypatch, 50)

        _make_file(users_dir / "1" / "trip" / "a" / "data.bin", 80)
        _make_file(users_dir / "2" / "trip" / "b" / "data.bin", 80)

        oldest_album = _make_album(1, "a", hours_ago=100)
        other_album = _make_album(2, "b", hours_ago=10)

        with _mock_eviction_albums(oldest_album, other_album):
            await run_eviction(skip_uid=1)

        assert (users_dir / "1" / "trip" / "a" / "data.bin").exists()
        assert not (users_dir / "2" / "trip" / "b").exists()

    async def test_stops_when_under_cap(
        self, tmp_path: Path, users_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_storage(tmp_path, monkeypatch, 120)

        _make_file(users_dir / "1" / "trip" / "a" / "data.bin", 80)
        _make_file(users_dir / "2" / "trip" / "b" / "data.bin", 80)
        _make_file(users_dir / "3" / "trip" / "c" / "data.bin", 80)

        albums = [
            _make_album(1, "a", hours_ago=72),
            _make_album(2, "b", hours_ago=48),
            _make_album(3, "c", hours_ago=24),
        ]

        with _mock_eviction_albums(*albums):
            await run_eviction(skip_uid=999)

        assert not (users_dir / "1" / "trip" / "a").exists()
        assert not (users_dir / "2" / "trip" / "b").exists()
        assert (users_dir / "3" / "trip" / "c" / "data.bin").exists()
