from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from structlog.testing import capture_logs

from app.logic.media_upgrade.pipeline import (
    MatchCompleted,
    _clear_caches,
    run_matching,
)
from app.models.google_photos import PickedMediaItem

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
    async def test_logs_aggregate_matching_diagnostics_after_hash_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        h = _make_hash(0)

        async def fake_local(
            _album_dir: Path, name: str, _cached_hash: object
        ) -> tuple[str, imagehash.ImageHash | None]:
            return name, None if name == "failed.jpg" else h

        async def fake_candidate(
            _download: object,
            item: PickedMediaItem,
            _tokens: object,
            _cached_hash: object,
        ) -> tuple[str, imagehash.ImageHash | None]:
            return item.id, None if item.id == "google-failed" else h

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_local_one", fake_local
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_candidate_one", fake_candidate
        )

        with capture_logs() as logs:
            events = [
                event
                async for event in run_matching(
                    clients=AsyncMock(),
                    album_dir=tmp_path,
                    media_by_step={1: ["matched.jpg", "failed.jpg"]},
                    step_ids=[1],
                    google_items=[
                        _make_item("google-matched", _match_dt(10, 5).isoformat()),
                        _make_item("google-failed", _match_dt(10, 6).isoformat()),
                    ],
                    tokens=_test_token,
                )
            ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert summary.matched == 1
        completed = next(
            log
            for log in logs
            if log.get("event") == "google_photos.matching.completed"
        )
        timings = {
            key: completed.pop(key)
            for key in (
                "local_hash_ms",
                "candidate_hash_ms",
                "assignment_ms",
                "total_ms",
            )
        }
        assert all(isinstance(value, int) and value >= 0 for value in timings.values())
        assert completed == {
            "event": "google_photos.matching.completed",
            "log_level": "info",
            "picked": 2,
            "matchable_picked": 2,
            "relevant_local": 2,
            "local_hashed": 1,
            "candidate_hashed": 1,
            "valid_edges": 1,
            "matched": 1,
            "unmatched_local": 0,
            "nearest_13_to_15": 0,
            "local_hash_database_hits": 0,
            "local_hash_cache_hits": 0,
            "local_hash_cache_misses": 2,
            "candidate_hash_cache_hits": 0,
            "candidate_hash_cache_misses": 2,
        }

    async def test_matches_picked_items_regardless_of_timestamp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hashes = {
            "inside.jpg": _make_hash(0),
            "outside.jpg": _make_hash((1 << 64) - 1),
        }

        async def fake_local(
            _album_dir: Path, name: str, _cached_hash: object
        ) -> tuple[str, imagehash.ImageHash]:
            return name, hashes[name]

        async def fake_candidate(
            _download: object,
            item: PickedMediaItem,
            _tokens: object,
            _cached_hash: object,
        ) -> tuple[str, imagehash.ImageHash]:
            local_name = f"{item.id.removeprefix('google-')}.jpg"
            return item.id, hashes[local_name]

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_local_one", fake_local
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_candidate_one", fake_candidate
        )

        events = [
            event
            async for event in run_matching(
                clients=AsyncMock(),
                album_dir=tmp_path,
                media_by_step={1: ["inside.jpg", "outside.jpg"]},
                step_ids=[1],
                google_items=[
                    _make_item("google-inside", _match_dt(10, 5).isoformat()),
                    _make_item("google-outside", "2024-01-20T10:00:00+00:00"),
                ],
                tokens=_test_token,
            )
        ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert {match.google_id for match in summary.matches} == {
            "google-inside",
            "google-outside",
        }

    async def test_hashes_all_album_media_regardless_of_picker_timestamps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hashes = {
            "first.jpg": _make_hash(0),
            "second.jpg": _make_hash((1 << 64) - 1),
        }
        hashed_local_names: list[str] = []

        async def fake_local(
            _album_dir: Path, name: str, _cached_hash: object
        ) -> tuple[str, imagehash.ImageHash]:
            hashed_local_names.append(name)
            return name, hashes[name]

        async def fake_candidate(
            _download: object,
            item: PickedMediaItem,
            _tokens: object,
            _cached_hash: object,
        ) -> tuple[str, imagehash.ImageHash]:
            return item.id, hashes["second.jpg"]

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_local_one", fake_local
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline._hash_candidate_one", fake_candidate
        )

        events = [
            event
            async for event in run_matching(
                clients=AsyncMock(),
                album_dir=tmp_path,
                media_by_step={1: ["first.jpg"], 2: ["second.jpg"]},
                step_ids=[1, 2],
                google_items=[
                    _make_item("google-second", _match_dt(10, 30).isoformat())
                ],
                tokens=_test_token,
            )
        ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert set(hashed_local_names) == {"first.jpg", "second.jpg"}
        assert [(match.local_name, match.google_id) for match in summary.matches] == [
            ("second.jpg", "google-second")
        ]
