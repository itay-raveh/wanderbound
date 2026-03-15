"""Tests for thumbnail generation (media.py)."""

import io
from pathlib import Path

import pytest
from PIL import Image

from app.logic.layout.media import THUMB_QUALITY, THUMB_WIDTHS, generate_thumbnails
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


# generate_thumbnails


class TestGenerateThumbnails:
    @pytest.mark.anyio
    async def test_creates_all_expected_widths(self, tmp_path: Path) -> None:
        """All thumbnail widths are generated for a large image."""
        src = create_test_jpeg(tmp_path / "photo.jpg", 4000, 3000)
        await generate_thumbnails(src)

        for w in THUMB_WIDTHS:
            thumb = tmp_path / ".thumbs" / str(w) / "photo.webp"
            assert thumb.exists(), f"Missing thumbnail at width {w}"
            with Image.open(thumb) as img:
                assert img.width == w
                assert img.format == "WEBP"

    @pytest.mark.anyio
    async def test_preserves_aspect_ratio(self, tmp_path: Path) -> None:
        """Thumbnails maintain the original aspect ratio."""
        src = create_test_jpeg(tmp_path / "wide.jpg", 4000, 2000)
        await generate_thumbnails(src)

        original_ratio = 4000 / 2000
        for w in THUMB_WIDTHS:
            with Image.open(tmp_path / ".thumbs" / str(w) / "wide.webp") as img:
                thumb_ratio = img.width / img.height
                assert abs(thumb_ratio - original_ratio) < 0.02

    @pytest.mark.anyio
    async def test_skips_widths_larger_than_original(self, tmp_path: Path) -> None:
        """No thumbnail created when the requested width >= original width."""
        src = create_test_jpeg(tmp_path / "small.jpg", 600, 400)
        await generate_thumbnails(src)

        # 600px original: only 400 should be generated
        assert (tmp_path / ".thumbs" / "400" / "small.webp").exists()
        assert not (tmp_path / ".thumbs" / "1200" / "small.webp").exists()

    @pytest.mark.anyio
    async def test_no_thumbnails_for_tiny_image(self, tmp_path: Path) -> None:
        """An image smaller than all thumbnail widths produces no thumbs."""
        src = create_test_jpeg(tmp_path / "tiny.jpg", 200, 150)
        await generate_thumbnails(src)

        assert not (tmp_path / ".thumbs").exists()

    @pytest.mark.anyio
    async def test_exact_width_match_skipped(self, tmp_path: Path) -> None:
        """An image exactly 400px wide should NOT get a 400px thumbnail."""
        src = create_test_jpeg(tmp_path / "exact.jpg", 400, 300)
        await generate_thumbnails(src)

        assert not (tmp_path / ".thumbs").exists()

    @pytest.mark.anyio
    async def test_idempotent(self, tmp_path: Path) -> None:
        """Running generate_thumbnails twice produces the same output."""
        src = create_test_jpeg(tmp_path / "img.jpg", 2000, 1500)
        await generate_thumbnails(src)

        first_sizes = {}
        for w in THUMB_WIDTHS:
            p = tmp_path / ".thumbs" / str(w) / "img.webp"
            if p.exists():
                first_sizes[w] = p.stat().st_size

        await generate_thumbnails(src)

        for w, size in first_sizes.items():
            p = tmp_path / ".thumbs" / str(w) / "img.webp"
            assert p.stat().st_size == size

    @pytest.mark.anyio
    async def test_multiple_images_share_thumbs_dir(self, tmp_path: Path) -> None:
        """Multiple images in the same directory share the .thumbs tree."""
        create_test_jpeg(tmp_path / "a.jpg", 3000, 2000)
        create_test_jpeg(tmp_path / "b.jpg", 3000, 2000)
        await generate_thumbnails(tmp_path / "a.jpg")
        await generate_thumbnails(tmp_path / "b.jpg")

        for w in THUMB_WIDTHS:
            d = tmp_path / ".thumbs" / str(w)
            assert (d / "a.webp").exists()
            assert (d / "b.webp").exists()

    @pytest.mark.anyio
    async def test_thumbnails_smaller_than_original(self, tmp_path: Path) -> None:
        """Each generated thumbnail is smaller in file size than the original."""
        src = create_test_jpeg(tmp_path / "big.jpg", 4000, 3000)
        orig_size = src.stat().st_size
        await generate_thumbnails(src)

        for w in THUMB_WIDTHS:
            thumb = tmp_path / ".thumbs" / str(w) / "big.webp"
            assert thumb.stat().st_size < orig_size

    @pytest.mark.anyio
    async def test_portrait_image(self, tmp_path: Path) -> None:
        """Portrait (tall) images are handled correctly."""
        src = create_test_jpeg(tmp_path / "portrait.jpg", 2000, 4000)
        await generate_thumbnails(src)

        for w in THUMB_WIDTHS:
            thumb = tmp_path / ".thumbs" / str(w) / "portrait.webp"
            assert thumb.exists()
            with Image.open(thumb) as img:
                assert img.width == w


class TestGenerateThumbnailsExif:
    """EXIF-rotated images produce thumbnails with the display dimensions."""

    @pytest.mark.anyio
    async def test_exif_rotated_image(self, tmp_path: Path) -> None:
        # Stored as 3000x4000 with rotation 6 → display is 4000x3000
        src = _create_jpeg_with_exif_rotation(tmp_path / "rotated.jpg", 3000, 4000)
        await generate_thumbnails(src)

        # After auto-rotation, logical width=4000 → all widths generated
        for w in THUMB_WIDTHS:
            thumb = tmp_path / ".thumbs" / str(w) / "rotated.webp"
            assert thumb.exists(), f"Missing rotated thumb at width {w}"
            with Image.open(thumb) as img:
                assert img.width == w


# Constants


class TestThumbnailConstants:
    def test_widths_sorted_ascending(self) -> None:
        assert list(THUMB_WIDTHS) == sorted(THUMB_WIDTHS)

    def test_quality_in_range(self) -> None:
        assert 1 <= THUMB_QUALITY <= 100
