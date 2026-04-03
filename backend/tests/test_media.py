import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.logic.layout.media import (
    Media,
    _video_dimensions,
    delete_thumbnails,
    extract_frame,
    generate_thumbnail,
)
from tests.factories import create_test_jpeg


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


def _thumb_path(parent: Path, width: int, stem: str) -> Path:
    return parent / ".thumbs" / str(width) / f"{stem}.webp"


class TestGenerateThumbnail:
    async def test_creates_thumbnail_at_requested_width(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "photo.jpg", 4000, 3000)
        result = await generate_thumbnail(src, 800)

        assert result is not None
        assert result.exists()
        with Image.open(result) as img:
            assert img.width == 800
            assert img.format == "WEBP"

    async def test_preserves_aspect_ratio(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "wide.jpg", 4000, 2000)
        result = await generate_thumbnail(src, 800)

        assert result is not None
        with Image.open(result) as img:
            assert abs(img.width / img.height - 4000 / 2000) < 0.02

    async def test_returns_none_when_width_exceeds_orig(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "small.jpg", 600, 400)
        result = await generate_thumbnail(src, 800)

        assert result is None

    async def test_returns_none_for_exact_width(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "exact.jpg", 200, 150)
        result = await generate_thumbnail(src, 200)

        assert result is None

    async def test_generates_only_requested_width(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "photo.jpg", 4000, 3000)
        await generate_thumbnail(src, 200)

        assert _thumb_path(tmp_path, 200, "photo").exists()
        assert not _thumb_path(tmp_path, 800, "photo").exists()

    async def test_multiple_images_share_thumbs_dir(self, tmp_path: Path) -> None:
        create_test_jpeg(tmp_path / "a.jpg", 3000, 2000)
        create_test_jpeg(tmp_path / "b.jpg", 3000, 2000)
        await generate_thumbnail(tmp_path / "a.jpg", 200)
        await generate_thumbnail(tmp_path / "b.jpg", 200)

        d = tmp_path / ".thumbs" / "200"
        assert (d / "a.webp").exists()
        assert (d / "b.webp").exists()


class TestGenerateThumbnailExif:
    async def test_exif_rotated_image(self, tmp_path: Path) -> None:
        # Stored as 3000x4000 with rotation 6 -> display is 4000x3000
        src = create_test_jpeg(tmp_path / "rotated.jpg", 3000, 4000, exif_orientation=6)
        result = await generate_thumbnail(src, 800)

        assert result is not None
        with Image.open(result) as img:
            assert img.width == 800


class TestDeleteThumbnails:
    async def test_deletes_existing_thumbnails(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "photo.jpg", 4000, 3000)
        await generate_thumbnail(src, 200)
        await generate_thumbnail(src, 800)

        assert _thumb_path(tmp_path, 200, "photo").exists()
        assert _thumb_path(tmp_path, 800, "photo").exists()

        delete_thumbnails(src)

        assert not _thumb_path(tmp_path, 200, "photo").exists()
        assert not _thumb_path(tmp_path, 800, "photo").exists()

    def test_noop_when_no_thumbnails_exist(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "photo.jpg", 4000, 3000)
        delete_thumbnails(src)  # should not raise
