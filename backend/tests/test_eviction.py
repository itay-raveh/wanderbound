from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import get_settings
from app.logic.eviction import _sizes_by_album, run_eviction
from app.models.album import Album
from app.models.user import User

from .factories import make_album, make_async_session_mock, make_user


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
    mock_result.all.return_value = [
        (album, MagicMock(id=album.uid, is_demo=False)) for album in albums
    ]
    mock_session = make_async_session_mock(exec=AsyncMock(return_value=mock_result))
    return patch("app.logic.eviction.AsyncSession", return_value=mock_session)


def _single_demo_eviction(
    users_dir: Path, *, commit_error: Exception | None = None
) -> tuple[User, MagicMock]:
    _make_file(users_dir / "1" / "trip" / "old" / "data.bin", 80)
    user = make_user(1, album_ids=["old"], is_demo=True)
    result = MagicMock()
    result.all.return_value = [(_make_album(1, "old", hours_ago=48), user)]
    session = make_async_session_mock(
        exec=AsyncMock(return_value=result),
        commit=AsyncMock(side_effect=commit_error),
    )
    return user, session


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

    async def test_evicts_entire_demo_user(
        self, tmp_path: Path, users_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_storage(tmp_path, monkeypatch, 100)

        _make_file(users_dir / "1" / "trip" / "old" / "data.bin", 80)
        _make_file(users_dir / "1" / "trip" / "recent" / "data.bin", 80)
        _make_file(users_dir / "2" / "trip" / "real" / "data.bin", 80)

        demo_user = make_user(1, album_ids=["old", "recent"], is_demo=True)
        real_user = make_user(2, album_ids=["real"])
        old_album = _make_album(1, "old", hours_ago=48)
        recent_album = _make_album(1, "recent", hours_ago=1)
        real_album = _make_album(2, "real", hours_ago=24)
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (old_album, demo_user),
            (real_album, real_user),
            (recent_album, demo_user),
        ]
        mock_session = make_async_session_mock(exec=AsyncMock(return_value=mock_result))

        with patch("app.logic.eviction.AsyncSession", return_value=mock_session):
            await run_eviction(skip_uid=999)

        mock_session.delete.assert_awaited_once_with(demo_user)
        mock_session.commit.assert_awaited_once()
        assert not (users_dir / "1").exists()
        assert (users_dir / "2" / "trip" / "real" / "data.bin").exists()

    async def test_resumes_demo_eviction_after_commit_failure(
        self, tmp_path: Path, users_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_storage(tmp_path, monkeypatch, 50)

        demo_user, failed_session = _single_demo_eviction(
            users_dir, commit_error=OSError("commit failed")
        )

        with (
            patch("app.logic.eviction.AsyncSession", return_value=failed_session),
            pytest.raises(OSError, match="commit failed"),
        ):
            await run_eviction(skip_uid=999)

        pending = next((users_dir / ".evictions").iterdir())
        assert pending.exists()
        assert not (users_dir / "1").exists()

        skipped_session = make_async_session_mock(get=AsyncMock(return_value=demo_user))
        with patch("app.logic.eviction.AsyncSession", return_value=skipped_session):
            await run_eviction(skip_uid=1)

        skipped_session.delete.assert_not_awaited()
        assert pending.exists()

        recovery_session = make_async_session_mock(
            get=AsyncMock(return_value=demo_user)
        )
        with patch("app.logic.eviction.AsyncSession", return_value=recovery_session):
            await run_eviction(skip_uid=999)

        recovery_session.delete.assert_awaited_once_with(demo_user)
        recovery_session.commit.assert_awaited_once()
        assert not pending.exists()

    async def test_resumes_demo_eviction_after_cleanup_failure(
        self, tmp_path: Path, users_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_storage(tmp_path, monkeypatch, 50)

        _, failed_session = _single_demo_eviction(users_dir)

        with (
            patch("app.logic.eviction.AsyncSession", return_value=failed_session),
            patch(
                "app.logic.eviction._remove_tree",
                side_effect=OSError("cleanup failed"),
            ),
            pytest.raises(OSError, match="cleanup failed"),
        ):
            await run_eviction(skip_uid=999)

        pending = next((users_dir / ".evictions").iterdir())
        failed_session.commit.assert_awaited_once()
        assert pending.exists()

        recovery_session = make_async_session_mock(get=AsyncMock(return_value=None))
        with patch("app.logic.eviction.AsyncSession", return_value=recovery_session):
            await run_eviction(skip_uid=999)

        recovery_session.delete.assert_not_awaited()
        assert not pending.exists()

    async def test_does_not_delete_newer_demo_session_during_recovery(
        self, tmp_path: Path, users_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_storage(tmp_path, monkeypatch, 50)

        demo_user, failed_session = _single_demo_eviction(
            users_dir, commit_error=OSError("commit failed")
        )

        with (
            patch("app.logic.eviction.AsyncSession", return_value=failed_session),
            pytest.raises(OSError, match="commit failed"),
        ):
            await run_eviction(skip_uid=999)

        pending = next((users_dir / ".evictions").iterdir())
        newer_user = make_user(
            1,
            album_ids=["new"],
            is_demo=True,
            last_active_at=demo_user.last_active_at + timedelta(hours=1),
        )
        recovery_session = make_async_session_mock(
            get=AsyncMock(return_value=newer_user)
        )
        with patch("app.logic.eviction.AsyncSession", return_value=recovery_session):
            await run_eviction(skip_uid=999)

        recovery_session.delete.assert_not_awaited()
        assert not pending.exists()
        assert (users_dir / "1").exists()

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
