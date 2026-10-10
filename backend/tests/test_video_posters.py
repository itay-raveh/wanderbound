import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from app.api.v1.routes import assets
from app.core.config import get_settings
from tests.factories import DEFAULT_MEDIA_NAME, make_user


async def test_lazy_poster_request_cannot_overwrite_a_selected_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    user = make_user()
    album_dir = user.trips_folder / "trip"
    album_dir.mkdir(parents=True)
    video = album_dir / DEFAULT_MEDIA_NAME.replace(".jpg", ".mp4")
    video.write_bytes(b"video")
    poster = video.with_suffix(".jpg")
    poster.write_bytes(b"old poster")
    selecting = asyncio.Event()
    finish = asyncio.Event()
    requested = asyncio.Event()

    async def probe(function: Callable[[], bool]) -> bool:
        result = function()
        if function == poster.is_file:
            requested.set()
        return result

    async def extract(path: Path, timestamp: float | None = None) -> Path:
        if timestamp is not None:
            selecting.set()
            await finish.wait()
        path.with_suffix(".jpg").write_bytes(
            b"selected frame" if timestamp is not None else b"default frame"
        )
        return path.with_suffix(".jpg")

    monkeypatch.setattr(assets, "extract_frame", extract)
    monkeypatch.setattr(assets, "run_sync", probe)
    selection = asyncio.create_task(
        assets.update_video_frame("trip", video.name, user, 1)
    )
    await selecting.wait()
    request = asyncio.create_task(assets._ensure_poster(poster, video, poster.name))
    await requested.wait()
    try:
        assert not request.done()
    finally:
        finish.set()
        await asyncio.gather(selection, request)
    assert poster.read_bytes() == b"selected frame"
