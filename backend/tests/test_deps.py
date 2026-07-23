from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from cachetools import TTLCache
from fastapi import BackgroundTasks

from app.api.v1 import deps
from app.core.config import get_settings

from .factories import make_user

if TYPE_CHECKING:
    import pytest


def test_activity_debounce_uses_bounded_ttl_cache() -> None:
    assert isinstance(deps._last_activity_write, TTLCache)
    assert deps._last_activity_write.maxsize == 1024
    assert deps._last_activity_write.ttl == 3600


async def test_activity_write_can_be_scheduled_after_ttl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 0.0
    cache: TTLCache[int, None] = TTLCache(
        maxsize=1024,
        ttl=3600,
        timer=lambda: now,
    )
    monkeypatch.setattr(deps, "_last_activity_write", cache)
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    user = make_user()
    monkeypatch.setattr(deps, "try_load_user", AsyncMock(return_value=user))
    request = MagicMock()
    session = AsyncMock()
    background = BackgroundTasks()

    await deps.require_loaded_user(request, session, background)
    await deps.require_loaded_user(request, session, background)
    assert len(background.tasks) == 1
    assert cache[user.id] is None

    now = 3601.0
    await deps.require_loaded_user(request, session, background)
    assert len(background.tasks) == 2
