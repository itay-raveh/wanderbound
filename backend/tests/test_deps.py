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

from .conftest import make_async_session_mock


@pytest.fixture(autouse=True)
def _clean_activity_cache() -> None:
    _last_activity_write.clear()


class TestTouchActivity:
    async def test_executes_update(self) -> None:
        mock_session = make_async_session_mock()

        with patch("app.api.v1.deps.AsyncSession", return_value=mock_session):
            await _touch_activity(42)

        mock_session.exec.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    async def test_swallows_exceptions(self) -> None:
        mock_session = make_async_session_mock()
        mock_session.exec = AsyncMock(
            side_effect=OperationalError("SELECT", {}, Exception("db down"))
        )

        with patch("app.api.v1.deps.AsyncSession", return_value=mock_session):
            await _touch_activity(42)


class TestGetUserDebounce:
    def _make_request(self, uid: int) -> MagicMock:
        request = MagicMock()
        request.session = {"uid": uid}
        return request

    async def test_first_call_triggers_activity(self) -> None:
        user = MagicMock()
        user.id = 1

        session = AsyncMock()
        session.get = AsyncMock(return_value=user)

        bg = BackgroundTasks()
        result = await _get_user(self._make_request(1), session, bg)

        assert result is user
        assert 1 in _last_activity_write
        assert len(bg.tasks) == 1

    async def test_repeated_call_within_debounce_skips(self) -> None:
        user = MagicMock()
        user.id = 2

        session = AsyncMock()
        session.get = AsyncMock(return_value=user)

        # Pretend we just wrote
        _last_activity_write[2] = time.monotonic()

        bg = BackgroundTasks()
        await _get_user(self._make_request(2), session, bg)
        assert len(bg.tasks) == 0

    async def test_call_after_debounce_triggers(self) -> None:
        user = MagicMock()
        user.id = 3

        session = AsyncMock()
        session.get = AsyncMock(return_value=user)

        # Set last write to well beyond the debounce window
        _last_activity_write[3] = time.monotonic() - _ACTIVITY_DEBOUNCE_SECS - 1

        bg = BackgroundTasks()
        await _get_user(self._make_request(3), session, bg)
        assert len(bg.tasks) == 1
