"""Tests for thumbnail serving via the ?w= query param on the media endpoint."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.routes.assets import get_media, update_video_frame
from app.logic.layout.media import THUMB_WIDTHS, generate_thumbnails
from tests.conftest import create_test_jpeg

# ── Helpers ──────────────────────────────────────────────────────────────────

_AID = "test-album-id"
_NAME = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb.jpg"
_NAME_MP4 = (
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb.mp4"
)


def _mock_user(trips_folder: Path) -> MagicMock:
    user = MagicMock()
    user.trips_folder = trips_folder
    return user


async def _setup_album_with_thumbs(trips_folder: Path) -> Path:
    """Create a JPEG in an album dir and generate its thumbnails."""
    album_dir = trips_folder / _AID
    src = create_test_jpeg(album_dir / _NAME, 4000, 3000)
    await generate_thumbnails(src)
    return album_dir


# ── get_media with ?w= ──────────────────────────────────────────────────────


class TestGetMediaThumbnail:
    @pytest.mark.anyio
    async def test_serves_thumbnail_when_w_specified(self, tmp_path: Path) -> None:
        """?w=1200 returns the WebP thumbnail."""
        album_dir = await _setup_album_with_thumbs(tmp_path)
        user = _mock_user(tmp_path)

        response = await get_media(_AID, _NAME, user, w=1200)

        stem = Path(_NAME).stem
        thumb_path = album_dir / ".thumbs" / "1200" / f"{stem}.webp"
        assert Path(response.path) == thumb_path
        assert response.media_type == "image/webp"

    @pytest.mark.anyio
    async def test_serves_original_when_no_w(self, tmp_path: Path) -> None:
        """No ?w= param returns the original JPEG."""
        await _setup_album_with_thumbs(tmp_path)
        user = _mock_user(tmp_path)

        response = await get_media(_AID, _NAME, user, w=None)

        assert Path(response.path) == (tmp_path / _AID / _NAME).resolve()

    @pytest.mark.anyio
    async def test_falls_through_when_thumb_missing(self, tmp_path: Path) -> None:
        """If the thumbnail doesn't exist, fall through to original."""
        album_dir = tmp_path / _AID
        create_test_jpeg(album_dir / _NAME, 4000, 3000)
        user = _mock_user(tmp_path)

        response = await get_media(_AID, _NAME, user, w=1200)

        assert Path(response.path) == (album_dir / _NAME).resolve()

    @pytest.mark.anyio
    async def test_all_thumb_widths_servable(self, tmp_path: Path) -> None:
        """All thumbnail widths can be served."""
        await _setup_album_with_thumbs(tmp_path)
        user = _mock_user(tmp_path)

        for w in THUMB_WIDTHS:
            response = await get_media(_AID, _NAME, user, w=w)
            mt = response.media_type or ""
            assert "webp" in mt or str(response.path).endswith(".webp")

    @pytest.mark.anyio
    async def test_cache_header_on_thumbnail(self, tmp_path: Path) -> None:
        """Thumbnails get the same immutable cache header as originals."""
        await _setup_album_with_thumbs(tmp_path)
        user = _mock_user(tmp_path)

        response = await get_media(_AID, _NAME, user, w=1200)

        assert "immutable" in response.headers["cache-control"]

    @pytest.mark.anyio
    async def test_ignores_invalid_width(self, tmp_path: Path) -> None:
        """?w= with a non-standard width serves the original."""
        await _setup_album_with_thumbs(tmp_path)
        user = _mock_user(tmp_path)

        response = await get_media(_AID, _NAME, user, w=9999)

        assert Path(response.path) == (tmp_path / _AID / _NAME).resolve()

    @pytest.mark.anyio
    async def test_falls_through_for_small_original(self, tmp_path: Path) -> None:
        """If original is 600px, ?w=1200 falls through (no thumb)."""
        album_dir = tmp_path / _AID
        src = create_test_jpeg(album_dir / _NAME, 600, 400)
        await generate_thumbnails(src)  # only creates 400px thumb
        user = _mock_user(tmp_path)

        response = await get_media(_AID, _NAME, user, w=1200)

        # Should fall through to original
        assert Path(response.path) == (album_dir / _NAME).resolve()


# ── update_video_frame regenerates thumbnails ───────────────────────────────


class TestUpdateVideoFrameRegeneratesThumbnails:
    @pytest.mark.anyio
    async def test_thumbnails_regenerated_after_frame_update(
        self, tmp_path: Path
    ) -> None:
        """PATCH to update video frame also regenerates poster thumbnails."""
        album_dir = tmp_path / _AID
        # Create the .mp4 file (just needs to exist for _resolve_media)
        video_path = album_dir / _NAME_MP4
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.touch()

        # Create a poster jpg that extract_frame would produce
        poster_path = video_path.with_suffix(".jpg")
        create_test_jpeg(poster_path, 3000, 2000)

        user = _mock_user(tmp_path)

        with (
            patch(
                "app.api.v1.routes.assets.extract_frame",
                AsyncMock(return_value=poster_path),
            ),
            patch(
                "app.api.v1.routes.assets.generate_thumbnails",
                wraps=generate_thumbnails,
            ) as mock_gen,
        ):
            await update_video_frame(_AID, _NAME_MP4, user, timestamp=2.5)

        mock_gen.assert_called_once_with(poster_path)

        # Verify thumbnails actually exist
        for w in THUMB_WIDTHS:
            stem = poster_path.stem
            thumb = album_dir / ".thumbs" / str(w) / f"{stem}.webp"
            assert thumb.exists()
