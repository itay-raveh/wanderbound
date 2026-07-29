import asyncio
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.logic.media_upgrade.phash_matching import (
    MatchResult,
)
from app.logic.media_upgrade.pipeline import (
    UpgradeCompleted,
    _clear_caches,
    run_upgrade,
)

from .media_upgrade_helpers import (
    make_item as _make_item,
    match_datetime as _match_dt,
    test_token as _test_token,
)


@pytest.fixture(autouse=True)
def _clear_upgrade_caches_between_tests() -> Iterator[None]:
    yield
    _clear_caches()


class TestRunUpgrade:
    @pytest.mark.parametrize(
        ("google_width", "google_height", "downloads"),
        [
            (1200, 800, False),
            (800, 600, False),
            (1600, 900, True),
            (None, None, True),
        ],
    )
    async def test_downloads_only_when_picker_metadata_may_be_larger(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        google_width: int | None,
        google_height: int | None,
        *,
        downloads: bool,
    ) -> None:
        download_and_replace = AsyncMock(return_value=True)
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._download_and_replace",
            download_and_replace,
        )
        persist_upgrade = AsyncMock()
        cleanup_picker_sessions = AsyncMock()
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._persist_upgrade", persist_upgrade
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._cleanup_picker_sessions",
            cleanup_picker_sessions,
        )
        match = MatchResult(
            local_name="photo.jpg", google_id="google-photo", distance=0
        )

        events = [
            event
            async for event in run_upgrade(
                clients=AsyncMock(),
                uid=1,
                aid="album",
                album_dir=tmp_path,
                matches=[match],
                google_items_by_id={
                    "google-photo": _make_item(
                        "google-photo",
                        _match_dt(10).isoformat(),
                        width=google_width,
                        height=google_height,
                    )
                },
                upgrade_candidates={"photo.jpg"},
                local_dimensions={"photo.jpg": (1200, 800)},
                tokens=_test_token,
                session_ids=[],
            )
        ]

        if downloads:
            download_and_replace.assert_awaited_once()
        else:
            download_and_replace.assert_not_awaited()
        persist_upgrade.assert_awaited_once()
        cleanup_picker_sessions.assert_awaited_once()
        assert not (tmp_path / ".upgrade-tmp").exists()
        assert events[-1] == UpgradeCompleted(
            replaced=int(downloads),
            skipped=int(not downloads),
            failed=0,
        )

    async def test_serializes_upgrade_file_lifecycles_with_two_gib_limit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline.detect_memory_mb", lambda: 2048
        )
        _clear_caches()
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        second_started = asyncio.Event()
        calls = 0

        async def fake_replace(*_args: object, **_kwargs: object) -> bool:
            nonlocal calls
            calls += 1
            if calls == 1:
                first_started.set()
                await release_first.wait()
            else:
                second_started.set()
            return True

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._download_and_replace", fake_replace
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._persist_upgrade", AsyncMock()
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._cleanup_picker_sessions", AsyncMock()
        )

        names = [
            f"00000000-0000-4000-8000-{i:012d}_"
            f"00000000-0000-4000-8000-{i + 10:012d}.jpg"
            for i in range(2)
        ]
        matches = [
            MatchResult(local_name=name, google_id=f"gp-{i}", distance=0)
            for i, name in enumerate(names)
        ]
        items = {
            f"gp-{i}": _make_item(f"gp-{i}", _match_dt(10).isoformat())
            for i in range(2)
        }

        async def collect() -> list[object]:
            return [
                event
                async for event in run_upgrade(
                    clients=AsyncMock(),
                    uid=1,
                    aid="album",
                    album_dir=tmp_path,
                    matches=matches,
                    google_items_by_id=items,
                    upgrade_candidates=set(names),
                    local_dimensions={},
                    tokens=_test_token,
                    session_ids=[],
                )
            ]

        task = asyncio.create_task(collect())
        try:
            await asyncio.wait_for(first_started.wait(), timeout=1)
            await asyncio.sleep(0)
            assert not second_started.is_set()
        finally:
            release_first.set()
        events = await task

        assert second_started.is_set()
        assert isinstance(events[-1], UpgradeCompleted)
