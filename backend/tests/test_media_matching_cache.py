import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import get_settings
from app.logic.media_upgrade.phash_matching import (
    compute_phash_from_path,
)
from app.logic.media_upgrade.pipeline import (
    MatchCompleted,
    MatchInProgress,
    _clear_caches,
    run_matching,
)
from app.models.google_photos import PickedMediaItem

from .factories import create_test_jpeg
from .media_upgrade_helpers import (
    make_hash as _make_hash,
    make_item as _make_item,
    match_datetime as _match_dt,
    test_token as _test_token,
    write_jpeg as _write_jpeg,
)

if TYPE_CHECKING:
    import imagehash


@pytest.fixture(autouse=True)
def _clear_upgrade_caches_between_tests() -> Iterator[None]:
    yield
    _clear_caches()


class TestRunMatching:
    async def test_uses_database_hash_without_reading_local_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        media_hash = _make_hash(0x1234)

        async def fake_candidate(
            _download: object,
            item: PickedMediaItem,
            _tokens: object,
            _cached_hash: object,
        ) -> tuple[str, imagehash.ImageHash]:
            return item.id, media_hash

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_candidate_one", fake_candidate
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_local_one",
            AsyncMock(side_effect=AssertionError("local media was decoded")),
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline.local_hash_cache",
            MagicMock(side_effect=AssertionError("disk cache was opened")),
        )
        events = [
            event
            async for event in run_matching(
                clients=AsyncMock(),
                album_dir=tmp_path,
                media_by_step={1: ["photo.jpg"]},
                step_ids=[1],
                google_items=[_make_item("google-photo", _match_dt(10).isoformat())],
                tokens=_test_token,
                persisted_local_hashes={"photo.jpg": [str(media_hash)]},
            )
        ]

        assert isinstance(events[-1], MatchCompleted)
        assert events[-1].matched == 1

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
            "app.logic.media_upgrade.pipeline._hash_local_one", fake_local
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

    async def test_reuses_persisted_local_hashes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
        album_dir = tmp_path / "users" / "42" / "trip" / "album"
        album_dir.mkdir(parents=True)
        photo = album_dir / "photo.jpg"
        _write_jpeg(photo, 800, 600)
        expected_hash = compute_phash_from_path(photo)

        async def fake_candidate(
            _download: object,
            item: PickedMediaItem,
            _tokens: object,
            _cached_hash: object,
        ) -> tuple[str, imagehash.ImageHash]:
            return item.id, expected_hash

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_candidate_one", fake_candidate
        )

        async def match_once() -> MatchCompleted:
            events = [
                event
                async for event in run_matching(
                    clients=AsyncMock(),
                    album_dir=album_dir,
                    media_by_step={1: ["photo.jpg"]},
                    step_ids=[1],
                    google_items=[
                        _make_item("google-photo", _match_dt(10).isoformat())
                    ],
                    tokens=_test_token,
                )
            ]
            assert isinstance(events[-1], MatchCompleted)
            return events[-1]

        first = await match_once()

        assert first.matched == 1
        assert (
            tmp_path / "users" / "42" / ".media-hash-cache" / album_dir.name
        ).is_dir()
        with patch(
            "app.logic.media_upgrade.hash_cache.compute_phash_from_path",
            side_effect=AssertionError("local photo was rehashed"),
        ):
            second = await match_once()
        assert second.matched == 1

    async def test_invalidates_cached_hash_when_local_file_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        album_dir = tmp_path / "album"
        album_dir.mkdir()
        photo = album_dir / "photo.jpg"
        _write_jpeg(photo, 800, 600)

        async def fake_candidate(
            _download: object,
            item: PickedMediaItem,
            _tokens: object,
            _cached_hash: object,
        ) -> tuple[str, imagehash.ImageHash]:
            return item.id, _make_hash(0)

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_candidate_one", fake_candidate
        )

        async def match_once() -> None:
            _ = [
                event
                async for event in run_matching(
                    clients=AsyncMock(),
                    album_dir=album_dir,
                    media_by_step={1: ["photo.jpg"]},
                    step_ids=[1],
                    google_items=[
                        _make_item("google-photo", _match_dt(10).isoformat())
                    ],
                    tokens=_test_token,
                )
            ]

        await match_once()
        _write_jpeg(photo, 1200, 800)

        with patch(
            "app.logic.media_upgrade.hash_cache.compute_phash_from_path",
            wraps=compute_phash_from_path,
        ) as compute:
            await match_once()
        assert compute.call_count == 1

    async def test_reuses_persisted_candidate_hashes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        album_dir = tmp_path / "album"
        album_dir.mkdir()
        photo = create_test_jpeg(album_dir / "photo.jpg", 800, 600)
        download = AsyncMock(return_value=photo.read_bytes())
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline.download_media_bytes", download
        )

        async def match(item: PickedMediaItem) -> MatchCompleted:
            events = [
                event
                async for event in run_matching(
                    clients=AsyncMock(),
                    album_dir=album_dir,
                    media_by_step={1: ["photo.jpg"]},
                    step_ids=[1],
                    google_items=[item],
                    tokens=_test_token,
                )
            ]
            assert isinstance(events[-1], MatchCompleted)
            return events[-1]

        item = _make_item(
            "google-photo", _match_dt(10).isoformat(), width=800, height=600
        )
        assert (await match(item)).matched == 1
        assert (await match(item)).matched == 1
        assert download.await_count == 1

    async def test_invalidates_candidate_hash_when_metadata_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        album_dir = tmp_path / "album"
        album_dir.mkdir()
        photo = create_test_jpeg(album_dir / "photo.jpg", 800, 600)
        download = AsyncMock(return_value=photo.read_bytes())
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline.download_media_bytes", download
        )

        for width in (800, 801):
            _ = [
                event
                async for event in run_matching(
                    clients=AsyncMock(),
                    album_dir=album_dir,
                    media_by_step={1: ["photo.jpg"]},
                    step_ids=[1],
                    google_items=[
                        _make_item(
                            "google-photo",
                            _match_dt(10).isoformat(),
                            width=width,
                            height=600,
                        )
                    ],
                    tokens=_test_token,
                )
            ]

        assert download.await_count == 2
