"""Tests for thumbnail generation (media.py)."""

import io
from pathlib import Path

import pytest
from PIL import Image

from app.logic.layout.media import (
    THUMB_QUALITY,
    THUMB_WIDTHS,
    delete_thumbnails,
    generate_thumbnail,
)
from tests.conftest import create_test_jpeg

# Helpers


def _create_jpeg_with_exif_rotation(path: Path, width: int, height: int) -> Path:
    """Create a JPEG that is stored WxH but has EXIF orientation 6 (90° CW).

    The logical display dimensions are HxW.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), color="blue")
    # Build minimal EXIF with orientation tag = 6
    exif = img.getexif()
    exif[0x0112] = 6  # Orientation tag
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())
    path.write_bytes(buf.getvalue())
    return path


def _thumb_path(parent: Path, width: int, stem: str) -> Path:
    return parent / ".thumbs" / str(width) / f"{stem}.webp"


class TestGenerateThumbnail:
    @pytest.mark.anyio
    async def test_creates_thumbnail_at_requested_width(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "photo.jpg", 4000, 3000)
        result = await generate_thumbnail(src, 800)

        assert result is not None
        assert result.exists()
        with Image.open(result) as img:
            assert img.width == 800
            assert img.format == "WEBP"

    @pytest.mark.anyio
    async def test_preserves_aspect_ratio(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "wide.jpg", 4000, 2000)
        result = await generate_thumbnail(src, 800)

        assert result is not None
        with Image.open(result) as img:
            assert abs(img.width / img.height - 4000 / 2000) < 0.02

    @pytest.mark.anyio
    async def test_returns_none_when_width_exceeds_orig(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "small.jpg", 600, 400)
        result = await generate_thumbnail(src, 800)

        assert result is None

    @pytest.mark.anyio
    async def test_returns_none_for_exact_width(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "exact.jpg", 200, 150)
        result = await generate_thumbnail(src, 200)

        assert result is None

    @pytest.mark.anyio
    async def test_generates_only_requested_width(self, tmp_path: Path) -> None:
        """Generating one width does not create the other."""
        src = create_test_jpeg(tmp_path / "photo.jpg", 4000, 3000)
        await generate_thumbnail(src, 200)

        assert _thumb_path(tmp_path, 200, "photo").exists()
        assert not _thumb_path(tmp_path, 800, "photo").exists()

    @pytest.mark.anyio
    async def test_thumbnail_smaller_than_original(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "big.jpg", 4000, 3000)
        result = await generate_thumbnail(src, 800)

        assert result is not None
        assert result.stat().st_size < src.stat().st_size

    @pytest.mark.anyio
    async def test_portrait_image(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "portrait.jpg", 2000, 4000)
        result = await generate_thumbnail(src, 200)

        assert result is not None
        with Image.open(result) as img:
            assert img.width == 200

    @pytest.mark.anyio
    async def test_multiple_images_share_thumbs_dir(self, tmp_path: Path) -> None:
        create_test_jpeg(tmp_path / "a.jpg", 3000, 2000)
        create_test_jpeg(tmp_path / "b.jpg", 3000, 2000)
        await generate_thumbnail(tmp_path / "a.jpg", 200)
        await generate_thumbnail(tmp_path / "b.jpg", 200)

        d = tmp_path / ".thumbs" / "200"
        assert (d / "a.webp").exists()
        assert (d / "b.webp").exists()


class TestGenerateThumbnailExif:
    @pytest.mark.anyio
    async def test_exif_rotated_image(self, tmp_path: Path) -> None:
        # Stored as 3000x4000 with rotation 6 -> display is 4000x3000
        src = _create_jpeg_with_exif_rotation(tmp_path / "rotated.jpg", 3000, 4000)
        result = await generate_thumbnail(src, 800)

        assert result is not None
        with Image.open(result) as img:
            assert img.width == 800


# delete_thumbnails


class TestDeleteThumbnails:
    @pytest.mark.anyio
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


# Constants


class TestThumbnailConstants:
    def test_widths_sorted_ascending(self) -> None:
        assert list(THUMB_WIDTHS) == sorted(THUMB_WIDTHS)

    def test_quality_in_range(self) -> None:
        assert 1 <= THUMB_QUALITY <= 100
