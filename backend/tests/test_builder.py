from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch
from uuid import uuid4

from app.core.config import get_settings
from app.logic.layout.builder import _load_photos, _step_media, build_step_layout
from app.logic.layout.media import Media
from app.models.polarsteps import Location, PSStep
from app.models.user import User
from tests.factories import collect_async, create_test_jpeg

if TYPE_CHECKING:
    import pytest

_AID = "south-america_123"


def _media_name(ext: str = "jpg") -> str:
    return f"{uuid4()}_{uuid4()}.{ext}"


def _make_step() -> PSStep:
    return PSStep(
        id=1,
        name="Test Step",
        slug="test-step",
        description="",
        timestamp=1_700_000_000.0,
        timezone_id="Europe/Amsterdam",
        location=Location(
            name="Test", detail="", country_code="nl", lat=52.37, lon=4.89
        ),
    )


def _make_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> User:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    return User(
        id=1,
        google_sub="g-1",
        first_name="Test",
        locale="en-US",
        unit_is_km=True,
        temperature_is_celsius=True,
    )


class TestLoadPhotos:
    def test_reads_correct_dimensions(self, tmp_path: Path) -> None:
        name = _media_name()
        create_test_jpeg(tmp_path / name, 1920, 1080)

        result = _load_photos(tmp_path)

        assert len(result) == 1
        assert result[0].width == 1920
        assert result[0].height == 1080


class TestStepMedia:
    async def test_photos_and_videos(self, tmp_path: Path) -> None:
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        jpg_name = _media_name()
        create_test_jpeg(photo_dir / jpg_name, 800, 600)

        video_dir = tmp_path / "videos"
        video_dir.mkdir()
        mp4_name = _media_name("mp4")
        (video_dir / mp4_name).write_bytes(b"\x00" * 100)

        async def fake_probe(path: Path) -> Media:
            return Media(name=path.name, width=3840, height=2160)

        with patch.object(Media, "probe", side_effect=fake_probe):
            result = await collect_async(_step_media(tmp_path))

        names = {m.name for m in result}
        assert len(result) == 2
        assert jpg_name in names
        assert mp4_name in names

    async def test_ignores_non_jpg_in_photos(self, tmp_path: Path) -> None:
        photo_dir = tmp_path / "photos"
        photo_dir.mkdir()
        (photo_dir / "notes.txt").write_text("hello")
        (photo_dir / "image.png").write_bytes(b"\x00" * 100)

        result = await collect_async(_step_media(tmp_path))
        assert result == []

    async def test_ignores_non_mp4_in_videos(self, tmp_path: Path) -> None:
        video_dir = tmp_path / "videos"
        video_dir.mkdir()
        (video_dir / "clip.avi").write_bytes(b"\x00" * 100)
        (video_dir / "clip.mov").write_bytes(b"\x00" * 100)

        result = await collect_async(_step_media(tmp_path))
        assert result == []


class TestBuildStepLayout:
    def _setup_step_dir(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> tuple[User, PSStep, Path]:
        user = _make_user(tmp_path, monkeypatch)
        step = _make_step()

        step_dir = tmp_path / "users" / str(user.id) / "trip" / _AID / step.folder_name
        step_dir.mkdir(parents=True)
        return user, step, step_dir

    async def test_portraits_and_landscapes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user, step, step_dir = self._setup_step_dir(tmp_path, monkeypatch)

        photo_dir = step_dir / "photos"
        photo_dir.mkdir()

        portrait_names = []
        for _ in range(2):
            n = _media_name()
            create_test_jpeg(photo_dir / n, 600, 1000)  # portrait
            portrait_names.append(n)

        landscape_names = []
        for _ in range(3):
            n = _media_name()
            create_test_jpeg(photo_dir / n, 1920, 1080)  # landscape
            landscape_names.append(n)

        layout = await build_step_layout(user, _AID, step)

        assert layout is not None
        assert layout.cover in portrait_names
        media_by_name = {m.name: m for m in layout.media}
        for name in portrait_names:
            assert media_by_name[name].is_portrait
        for name in landscape_names:
            assert not media_by_name[name].is_portrait
        flat = [name for page in layout.pages for name in page]
        assert sorted(flat) == sorted(portrait_names + landscape_names)

    async def test_photos_and_videos_mixed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user, step, step_dir = self._setup_step_dir(tmp_path, monkeypatch)

        photo_dir = step_dir / "photos"
        photo_dir.mkdir()
        jpg_name = _media_name()
        create_test_jpeg(photo_dir / jpg_name, 600, 1000)  # portrait

        video_dir = step_dir / "videos"
        video_dir.mkdir()
        vid_name = _media_name("mp4")
        (video_dir / vid_name).write_bytes(b"\x00" * 100)

        async def fake_probe(path: Path) -> Media:
            return Media(name=path.name, width=1920, height=1080)

        with patch.object(Media, "probe", side_effect=fake_probe):
            layout = await build_step_layout(user, _AID, step)

        assert layout is not None
        assert layout.cover == jpg_name
        media_by_name = {m.name: m for m in layout.media}
        assert media_by_name[jpg_name].is_portrait
        assert not media_by_name[vid_name].is_portrait
        flat = [name for page in layout.pages for name in page]
        assert sorted(flat) == sorted([jpg_name, vid_name])
