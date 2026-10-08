from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from PIL import Image

if TYPE_CHECKING:
    import httpx

from app.logic.media_upgrade.pipeline import (
    MatchCompleted,
    MatchInProgress,
    _clear_caches,
    run_matching,
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


class TestRunMatching:
    async def test_real_image_pairs_exclude_videos_and_mark_completed_upgrades(
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
        video = _make_item(
            "ready-video",
            _match_dt(10, 30).isoformat(),
            item_type="VIDEO",
            video_processing_status="READY",
            base_url="https://lh3.googleusercontent.com/video",
        )
        google_items.insert(0, video)
        (album_dir / "video.mp4").write_bytes(bytes_by_name[names[0]])
        url_to_bytes = {
            item.media_file.base_url: bytes_by_name[
                item.media_file.base_url.rsplit("/", 1)[-1]
            ]
            for item in google_items
            if item.type == "PHOTO"
        }

        url_to_bytes[video.media_file.base_url] = bytes_by_name[names[0]]

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
            "app.logic.media_upgrade.matching.download_media_bytes", fake_download
        )

        clients = AsyncMock()
        events = [
            event
            async for event in run_matching(
                clients=clients,
                album_dir=album_dir,
                media_by_step={
                    sid: [n, "video.mp4"]
                    for sid, n in zip(step_ids, names, strict=True)
                },
                step_ids=step_ids,
                google_items=google_items,
                tokens=_test_token,
                upgrade_candidates={names[0], names[2]},
            )
        ]

        summary = events[-1]
        assert isinstance(summary, MatchCompleted)
        assert summary.total_picked == 3
        assert summary.matched == 3
        assert summary.unmatched == 0
        assert {(m.local_name, m.google_id, m.upgraded) for m in summary.matches} == {
            ("step1.jpg", "gp-0", False),
            ("step2.jpg", "gp-1", True),
            ("step3.jpg", "gp-2", False),
        }

        progress = [e for e in events[:-1] if isinstance(e, MatchInProgress)]
        assert {(e.phase, e.total) for e in progress} == {
            ("preparing", 3),
            ("matching", 3),
        }
