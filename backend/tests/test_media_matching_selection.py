from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from PIL import Image

if TYPE_CHECKING:
    import httpx
    import imagehash

from app.logic.media_upgrade.pipeline import (
    MatchCompleted,
    MatchInProgress,
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


@pytest.fixture(autouse=True)
def _clear_upgrade_caches_between_tests() -> Iterator[None]:
    yield
    _clear_caches()


class TestRunMatching:
    async def test_excludes_all_videos_from_automatic_matching(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        h = _make_hash(0)
        hashed_local_names: list[str] = []
        hashed_candidate_ids: list[str] = []

        async def fake_local(
            _album_dir: Path, name: str, _cached_hash: object
        ) -> tuple[str, imagehash.ImageHash]:
            hashed_local_names.append(name)
            return name, h

        async def fake_candidate(
            _download: object,
            item: PickedMediaItem,
            _tokens: object,
            _cached_hash: object,
        ) -> tuple[str, imagehash.ImageHash]:
            hashed_candidate_ids.append(item.id)
            return item.id, h

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
                media_by_step={1: ["photo.jpg", "video.mp4"]},
                step_ids=[1],
                google_items=[
                    _make_item(
                        "ready-video",
                        _match_dt(10, 5).isoformat(),
                        item_type="VIDEO",
                        video_processing_status="READY",
                    ),
                    _make_item("ready-photo", _match_dt(10, 6).isoformat()),
                ],
                tokens=_test_token,
            )
        ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert hashed_local_names == ["photo.jpg"]
        assert hashed_candidate_ids == ["ready-photo"]
        assert summary.total_picked == 1
        assert summary.matched == 1
        assert summary.unmatched == 0
        assert [
            event.total
            for event in events
            if isinstance(event, MatchInProgress) and event.phase == "matching"
        ] == [1]
        assert [
            event.total
            for event in events
            if isinstance(event, MatchInProgress) and event.phase == "preparing"
        ] == [1]

    async def test_marks_matches_outside_upgrade_candidates_as_upgraded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        album_dir = tmp_path / "album"
        album_dir.mkdir()
        (album_dir / "photo.jpg").write_bytes(b"fake")
        h = _make_hash(0)

        async def fake_local(
            _album_dir: Path, name: str, _cached_hash: object
        ) -> tuple[str, imagehash.ImageHash]:
            return name, h

        async def fake_candidate(*_args: object) -> tuple[str, imagehash.ImageHash]:
            return "gp-1", h

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
                album_dir=album_dir,
                media_by_step={1: ["photo.jpg"]},
                step_ids=[1],
                google_items=[_make_item("gp-1", _match_dt(10, 5).isoformat())],
                tokens=_test_token,
                upgrade_candidates=set(),
            )
        ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert summary.matches[0].upgraded is True

    async def test_matches_real_images_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        album_dir = tmp_path / "album"
        album_dir.mkdir()

        step_ids = [1, 2, 3]
        names = ["step1.jpg", "step2.jpg", "step3.jpg"]

        bytes_by_name: dict[str, bytes] = {}
        for i, name in enumerate(names):
            img = Image.new("RGB", (400, 300))
            for y in range(300):
                for x in range(400):
                    img.putpixel(
                        (x, y),
                        ((x + i * 100) % 256, (y + i * 50) % 256, (i * 80) % 256),
                    )
            path = album_dir / name
            img.save(path, "JPEG", quality=90)
            bytes_by_name[name] = path.read_bytes()

        google_items = [
            _make_item(
                f"gp-{i}",
                _match_dt(10 + i * 4, 30).isoformat(),
                base_url=f"https://lh3.googleusercontent.com/{name}",
            )
            for i, name in enumerate(names)
        ]
        url_to_bytes = {
            item.media_file.base_url: bytes_by_name[names[i]]
            for i, item in enumerate(google_items)
        }

        async def fake_download(
            _client: httpx.AsyncClient,
            base_url: str,
            _access_token: str,
            *,
            param: str = "=d",
            max_bytes: int = 0,
        ) -> bytes:
            return url_to_bytes[base_url]

        monkeypatch.setattr(
            "app.logic.media_upgrade.pipeline.download_media_bytes", fake_download
        )

        clients = AsyncMock()
        events = [
            event
            async for event in run_matching(
                clients=clients,
                album_dir=album_dir,
                media_by_step={
                    sid: [n] for sid, n in zip(step_ids, names, strict=True)
                },
                step_ids=step_ids,
                google_items=google_items,
                tokens=_test_token,
            )
        ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert summary.total_picked == 3
        assert summary.matched == 3
        assert summary.unmatched == 0
        assert not any(m.upgraded for m in summary.matches)
        assert {m.local_name for m in summary.matches} == set(names)
        assert {m.google_id for m in summary.matches} == {"gp-0", "gp-1", "gp-2"}

        progress = [e for e in events[:-1] if isinstance(e, MatchInProgress)]
        assert {e.phase for e in progress} == {"preparing", "matching"}
