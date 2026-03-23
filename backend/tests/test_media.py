import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.logic.layout.media import (
    Media,
    _video_dimensions,
    extract_frame,
)
from tests.conftest import create_test_jpeg


def _ffprobe_output(
    width: int,
    height: int,
    tags: dict | None = None,
    side_data_list: list | None = None,
) -> bytes:
    stream: dict = {"width": width, "height": height, "tags": tags or {}}
    if side_data_list is not None:
        stream["side_data_list"] = side_data_list
    return json.dumps({"streams": [stream]}).encode()


def _mock_ffprobe(stdout: bytes, returncode: int = 0, stderr: bytes = b"") -> AsyncMock:
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (stdout, stderr)
    mock_proc.returncode = returncode
    return mock_proc


class TestMedia:
    def test_exif_orientation_6_swaps_dimensions(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "rotated.jpg", 3000, 4000, exif_orientation=6)
        m = Media.load(src)
        assert m.width == 4000
        assert m.height == 3000

    def test_exif_orientation_8_swaps_dimensions(self, tmp_path: Path) -> None:
        src = create_test_jpeg(
            tmp_path / "rotated8.jpg", 3000, 4000, exif_orientation=8
        )
        m = Media.load(src)
        assert m.width == 4000
        assert m.height == 3000


class TestVideoProbing:
    async def test_modern_side_data_rotation_270(self) -> None:
        mock_proc = _mock_ffprobe(
            _ffprobe_output(1080, 1920, side_data_list=[{"rotation": -270}])
        )
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            w, h = await _video_dimensions(Path("test.mp4"))
        assert (w, h) == (1920, 1080)

    async def test_side_data_ignored_when_legacy_rotate_present(self) -> None:
        mock_proc = _mock_ffprobe(
            _ffprobe_output(
                1080,
                1920,
                tags={"rotate": "90"},
                side_data_list=[{"rotation": 0}],
            )
        )
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            w, h = await _video_dimensions(Path("test.mp4"))
        assert (w, h) == (1920, 1080)

    async def test_ffprobe_failure_raises(self) -> None:
        mock_proc = _mock_ffprobe(b"", returncode=1, stderr=b"ffprobe error")
        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            pytest.raises(RuntimeError, match="ffprobe failed"),
        ):
            await _video_dimensions(Path("test.mp4"))

    async def test_no_streams_raises(self) -> None:
        mock_proc = _mock_ffprobe(json.dumps({"streams": []}).encode())
        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            pytest.raises(RuntimeError, match="No video stream"),
        ):
            await _video_dimensions(Path("test.mp4"))

    async def test_negative_rotation_uses_abs(self) -> None:
        mock_proc = _mock_ffprobe(_ffprobe_output(1080, 1920, tags={"rotate": "-90"}))
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            w, h = await _video_dimensions(Path("test.mp4"))
        assert (w, h) == (1920, 1080)


class TestExtractFrame:
    async def test_raises_on_failure(self, tmp_path: Path) -> None:
        video = tmp_path / "clip.mp4"
        video.touch()

        mock_proc = _mock_ffprobe(b"", returncode=1, stderr=b"extraction error")

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            pytest.raises(RuntimeError, match="Failed to extract"),
        ):
            await extract_frame(video, timestamp=1)
