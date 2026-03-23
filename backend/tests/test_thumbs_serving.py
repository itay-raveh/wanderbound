from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.v1.routes.assets import get_media, update_video_frame
from app.logic.layout.media import THUMB_WIDTHS, generate_thumbnail
from tests.conftest import create_test_jpeg

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
    album_dir = trips_folder / _AID
    src = create_test_jpeg(album_dir / _NAME, 4000, 3000)
    for w in THUMB_WIDTHS:
        await generate_thumbnail(src, w)
    return album_dir


class TestLazyThumbnailGeneration:
    async def test_generates_thumbnail_on_first_request(self, tmp_path: Path) -> None:
        album_dir = tmp_path / _AID
        create_test_jpeg(album_dir / _NAME, 4000, 3000)
        user = _mock_user(tmp_path)

        response = await get_media(_AID, _NAME, user, w=800)

        stem = Path(_NAME).stem
        thumb_path = album_dir / ".thumbs" / "800" / f"{stem}.webp"
        assert thumb_path.exists()
        assert Path(response.path) == thumb_path
        assert response.media_type == "image/webp"

    async def test_serves_existing_thumbnail(self, tmp_path: Path) -> None:
        album_dir = await _setup_album_with_thumbs(tmp_path)
        user = _mock_user(tmp_path)

        response = await get_media(_AID, _NAME, user, w=800)

        stem = Path(_NAME).stem
        assert Path(response.path) == album_dir / ".thumbs" / "800" / f"{stem}.webp"
        assert response.media_type == "image/webp"

    async def test_serves_original_when_no_w(self, tmp_path: Path) -> None:
        album_dir = tmp_path / _AID
        create_test_jpeg(album_dir / _NAME, 4000, 3000)
        user = _mock_user(tmp_path)

        response = await get_media(_AID, _NAME, user, w=None)

        assert Path(response.path) == (album_dir / _NAME).resolve()

    async def test_falls_through_for_small_original(self, tmp_path: Path) -> None:
        album_dir = tmp_path / _AID
        create_test_jpeg(album_dir / _NAME, 600, 400)
        user = _mock_user(tmp_path)

        response = await get_media(_AID, _NAME, user, w=800)

        assert Path(response.path) == (album_dir / _NAME).resolve()

    async def test_ignores_invalid_width(self, tmp_path: Path) -> None:
        album_dir = tmp_path / _AID
        create_test_jpeg(album_dir / _NAME, 4000, 3000)
        user = _mock_user(tmp_path)

        response = await get_media(_AID, _NAME, user, w=9999)

        assert Path(response.path) == (album_dir / _NAME).resolve()

    async def test_all_thumb_widths_servable(self, tmp_path: Path) -> None:
        album_dir = tmp_path / _AID
        create_test_jpeg(album_dir / _NAME, 4000, 3000)
        user = _mock_user(tmp_path)

        for w in THUMB_WIDTHS:
            response = await get_media(_AID, _NAME, user, w=w)
            mt = response.media_type or ""
            assert "webp" in mt or str(response.path).endswith(".webp")


class TestLazyPosterExtraction:
    @staticmethod
    def _setup_poster(tmp_path: Path) -> tuple[Path, MagicMock, patch]:
        album_dir = tmp_path / _AID
        album_dir.mkdir(parents=True)
        (album_dir / _NAME_MP4).touch()
        poster_path = album_dir / _NAME
        user = _mock_user(tmp_path)

        async def _fake_extract(video: Path, timestamp: float = 1) -> Path:
            create_test_jpeg(poster_path, 1920, 1080)
            return poster_path

        return (
            poster_path,
            user,
            patch("app.api.v1.routes.assets.extract_frame", side_effect=_fake_extract),
        )

    async def test_extracts_poster_on_first_request(self, tmp_path: Path) -> None:
        poster_path, user, mock_patch = self._setup_poster(tmp_path)

        with mock_patch:
            response = await get_media(_AID, _NAME, user)

        assert poster_path.exists()
        assert Path(response.path) == poster_path.resolve()

    async def test_poster_thumbnail_triggers_both_extraction_and_thumb(
        self, tmp_path: Path
    ) -> None:
        poster_path, user, mock_patch = self._setup_poster(tmp_path)

        with mock_patch:
            response = await get_media(_AID, _NAME, user, w=200)

        stem = Path(_NAME).stem
        thumb = poster_path.parent / ".thumbs" / "200" / f"{stem}.webp"
        assert thumb.exists()
        assert response.media_type == "image/webp"


class TestUpdateVideoFrame:
    async def test_deletes_poster_and_thumbnails_then_reextracts(
        self, tmp_path: Path
    ) -> None:
        album_dir = tmp_path / _AID
        album_dir.mkdir(parents=True)
        video_path = album_dir / _NAME_MP4
        video_path.touch()

        poster_path = video_path.with_suffix(".jpg")
        create_test_jpeg(poster_path, 3000, 2000)
        # Pre-generate thumbnails
        for w in THUMB_WIDTHS:
            await generate_thumbnail(poster_path, w)

        user = _mock_user(tmp_path)

        with patch(
            "app.api.v1.routes.assets.extract_frame",
            AsyncMock(return_value=poster_path),
        ) as mock_extract:
            await update_video_frame(_AID, _NAME_MP4, user, timestamp=2.5)

        mock_extract.assert_called_once_with(video_path, 2.5)

        for w in THUMB_WIDTHS:
            stem = poster_path.stem
            thumb = album_dir / ".thumbs" / str(w) / f"{stem}.webp"
            assert not thumb.exists()
