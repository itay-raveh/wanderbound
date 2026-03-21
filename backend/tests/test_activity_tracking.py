"""Tests for debounced activity tracking in deps.py."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks
from sqlalchemy.exc import OperationalError

from app.api.v1.deps import (
    _ACTIVITY_DEBOUNCE_SECS,
    _get_user,
    _last_activity_write,
    _touch_activity,
)


@pytest.fixture(autouse=True)
def _clean_activity_cache() -> None:
    _last_activity_write.clear()


class TestTouchActivity:
    @pytest.mark.anyio
    async def test_executes_update(self) -> None:
        """_touch_activity issues an UPDATE statement."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.api.v1.deps.AsyncSession", return_value=mock_session):
            await _touch_activity(42)

        mock_session.exec.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_swallows_exceptions(self) -> None:
        """Errors are swallowed so the background task doesn't crash."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.exec = AsyncMock(
            side_effect=OperationalError("SELECT", {}, Exception("db down"))
        )

        with patch("app.api.v1.deps.AsyncSession", return_value=mock_session):
            # Should not raise
            await _touch_activity(42)


class TestGetUserDebounce:
    def _make_request(self, uid: int) -> MagicMock:
        request = MagicMock()
        request.session = {"uid": uid}
        return request

    @pytest.mark.anyio
    async def test_first_call_triggers_activity(self) -> None:
        """First request for a user schedules an activity background task."""
        user = MagicMock()
        user.id = 1

        session = AsyncMock()
        session.get = AsyncMock(return_value=user)

        bg = BackgroundTasks()
        result = await _get_user(self._make_request(1), session, bg)

        assert result is user
        assert 1 in _last_activity_write
        assert len(bg.tasks) == 1

    @pytest.mark.anyio
    async def test_repeated_call_within_debounce_skips(self) -> None:
        """Calls within the debounce window don't trigger another write."""
        user = MagicMock()
        user.id = 2

        session = AsyncMock()
        session.get = AsyncMock(return_value=user)

        # Pretend we just wrote
        _last_activity_write[2] = time.monotonic()

        bg = BackgroundTasks()
        await _get_user(self._make_request(2), session, bg)
        assert len(bg.tasks) == 0

    @pytest.mark.anyio
    async def test_call_after_debounce_triggers(self) -> None:
        """After the debounce window expires, a new write is triggered."""
        user = MagicMock()
        user.id = 3

        session = AsyncMock()
        session.get = AsyncMock(return_value=user)

        # Set last write to well beyond the debounce window
        _last_activity_write[3] = time.monotonic() - _ACTIVITY_DEBOUNCE_SECS - 1

        bg = BackgroundTasks()
        await _get_user(self._make_request(3), session, bg)
        assert len(bg.tasks) == 1
