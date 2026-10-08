import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.logic.media_upgrade.pipeline import (
    MatchInProgress,
    _clear_caches,
    run_matching,
)

from .factories import create_test_jpeg
from .media_upgrade_helpers import (
    make_hash as _make_hash,
    make_item as _make_item,
    match_datetime as _match_dt,
    test_token as _test_token,
)

if TYPE_CHECKING:
    import imagehash


@pytest.fixture(autouse=True)
def _clear_upgrade_caches_between_tests() -> Iterator[None]:
    yield
    _clear_caches()


class TestRunMatching:
    async def test_cancels_pending_hashes_when_stream_closes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for name in ("fast.jpg", "slow.jpg"):
            (tmp_path / name).write_bytes(b"image")
        slow_started = asyncio.Event()
        slow_cancelled = asyncio.Event()
        slow_tasks: list[asyncio.Task[object]] = []

        async def fake_local(
            _album_dir: Path, name: str, _cached_hash: object
        ) -> tuple[str, imagehash.ImageHash]:
            if name == "fast.jpg":
                await slow_started.wait()
                return name, _make_hash(0)
            task = asyncio.current_task()
            assert task is not None
            slow_tasks.append(task)
            slow_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                slow_cancelled.set()
                raise
            raise AssertionError("unreachable")

        monkeypatch.setattr(
            "app.logic.media_upgrade.matching._hash_local_one", fake_local
        )
        events = run_matching(
            clients=AsyncMock(),
            album_dir=tmp_path,
            media_by_step={1: ["fast.jpg", "slow.jpg"]},
            step_ids=[1],
            google_items=[],
            tokens=_test_token,
            persisted_local_hashes={"fast.jpg": None, "slow.jpg": None},
        )

        try:
            assert isinstance(await anext(events), MatchInProgress)
            await events.aclose()
            await asyncio.wait_for(slow_cancelled.wait(), timeout=0.1)
        finally:
            for task in slow_tasks:
                task.cancel()
            await asyncio.gather(*slow_tasks, return_exceptions=True)

    @pytest.mark.parametrize("changed", ["local_file", "candidate_metadata"])
    async def test_changed_media_cannot_reuse_a_stale_photo_match(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
    ) -> None:
        photo = create_test_jpeg(tmp_path / "photo.jpg", 800, 600)
        candidate_bytes = photo.read_bytes()
        candidate_width = 800

        async def download(*_args: object, **_kwargs: object) -> bytes:
            return candidate_bytes

        monkeypatch.setattr(
            "app.logic.media_upgrade.matching.download_media_bytes", download
        )

        async def match_once() -> list:
            events = [
                event
                async for event in run_matching(
                    clients=AsyncMock(),
                    album_dir=tmp_path,
                    media_by_step={1: ["photo.jpg"]},
                    step_ids=[1],
                    google_items=[
                        _make_item(
                            "google-photo",
                            _match_dt(10).isoformat(),
                            width=candidate_width,
                            height=600,
                        )
                    ],
                    tokens=_test_token,
                )
            ]
            return events[-1].matches

        assert [
            (match.local_name, match.google_id) for match in await match_once()
        ] == [("photo.jpg", "google-photo")]

        # A distinct, reproducible image makes stale identity observable in the
        # matching result, even if hashing and download internals are refactored.
        replacement = tmp_path / "replacement.jpg"
        Image.frombytes(
            "RGB",
            (32, 32),
            bytes((i * 37 + i * i // 17) % 256 for i in range(32 * 32 * 3)),
        ).resize((801, 600)).save(replacement, "JPEG")
        if changed == "local_file":
            replacement.replace(photo)
        else:
            candidate_bytes = replacement.read_bytes()
            candidate_width = 801

        assert await match_once() == []
