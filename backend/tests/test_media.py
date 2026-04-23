from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.logic.layout.media import (
    Media,
    delete_thumbnails,
    frame_to_oriented_image,
    generate_thumbnail,
)
from tests.factories import create_test_jpeg


class TestMedia:
    def test_exif_orientation_6_swaps_dimensions(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "rotated.jpg", 3000, 4000, exif_orientation=6)
        m = Media.load(src)
        assert m.width == 4000
        assert m.height == 3000


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

    async def test_returns_none_when_width_exceeds_orig(self, tmp_path: Path) -> None:
        src = create_test_jpeg(tmp_path / "small.jpg", 600, 400)
        result = await generate_thumbnail(src, 800)

        assert result is None


class TestGenerateThumbnailExif:
    async def test_exif_rotated_image(self, tmp_path: Path) -> None:
        # Stored as 3000x4000 with rotation 6 -> display is 4000x3000
        src = create_test_jpeg(tmp_path / "rotated.jpg", 3000, 4000, exif_orientation=6)
        result = await generate_thumbnail(src, 800)

        assert result is not None
        with Image.open(result) as img:
            assert img.width == 800


class TestFrameOrientation:
    @pytest.mark.parametrize(
        ("rotation", "expected_size"),
        [
            (0, (100, 50)),
            (90, (50, 100)),
            (180, (100, 50)),
            (270, (50, 100)),
            (-90, (50, 100)),
            (-180, (100, 50)),
        ],
    )
    def test_applies_frame_rotation(
        self, rotation: int, expected_size: tuple[int, int]
    ) -> None:
        original = Image.new("RGB", (100, 50), "red")
        fake_frame = SimpleNamespace(rotation=rotation, to_image=lambda: original)

        out = frame_to_oriented_image(fake_frame)
        assert out.size == expected_size


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
