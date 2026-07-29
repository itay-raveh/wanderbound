from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from PIL.ExifTags import Base as ExifBase

from app.logic.media_upgrade.processing import (
    _MAX_LONG_EDGE,
    _VIDEO_THREADS,
    process_photo_sync,
    process_video,
)

from .media_upgrade_helpers import (
    write_jpeg as _write_jpeg,
    write_png as _write_png,
)


class TestProcessPhoto:
    def test_strips_exif(self, tmp_path: Path) -> None:
        img = Image.new("RGB", (800, 600))
        exif = img.getexif()
        exif[ExifBase.Make] = "TestCamera"
        exif[ExifBase.Model] = "X100"
        exif[ExifBase.Software] = "TestSuite"
        exif_bytes = exif.tobytes()

        raw = tmp_path / "in.jpg"
        out = tmp_path / "out.jpg"
        _write_jpeg(raw, 800, 600, exif=exif_bytes)

        with Image.open(raw) as src:
            assert len(src.getexif()) > 0

        process_photo_sync(raw, out)

        with Image.open(out) as result:
            assert len(result.getexif()) == 0

    @pytest.mark.parametrize(
        ("source_size", "expected_size"),
        [
            ((5000, 3000), (_MAX_LONG_EDGE, 1800)),
            ((3000, 5000), (1800, _MAX_LONG_EDGE)),
            ((2000, 1500), (2000, 1500)),
        ],
    )
    def test_resizes_photos(
        self,
        tmp_path: Path,
        source_size: tuple[int, int],
        expected_size: tuple[int, int],
    ) -> None:
        raw = tmp_path / "in.jpg"
        out = tmp_path / "out.jpg"
        _write_jpeg(raw, *source_size)

        w, h = process_photo_sync(raw, out)

        assert (w, h) == expected_size
        with Image.open(out) as result:
            assert result.size == expected_size

    def test_retains_more_resolution_for_panorama(self, tmp_path: Path) -> None:
        raw = tmp_path / "in.jpg"
        out = tmp_path / "out.jpg"
        _write_jpeg(raw, 9000, 3000)

        size = process_photo_sync(raw, out)

        assert size == (8192, 2731)

    def test_converts_png_to_jpeg(self, tmp_path: Path) -> None:
        raw = tmp_path / "in.png"
        out = tmp_path / "out.jpg"
        _write_png(raw, 800, 600)

        w, h = process_photo_sync(raw, out)

        assert (w, h) == (800, 600)
        with Image.open(out) as result:
            assert result.format == "JPEG"
            assert result.size == (800, 600)

    def test_handles_orientation_tag(self, tmp_path: Path) -> None:
        img = Image.new("RGB", (400, 600))
        exif = img.getexif()
        exif[ExifBase.Orientation] = 6
        exif_bytes = exif.tobytes()

        raw = tmp_path / "in.jpg"
        out = tmp_path / "out.jpg"
        _write_jpeg(raw, 400, 600, exif=exif_bytes)

        w, h = process_photo_sync(raw, out)

        assert (w, h) == (600, 400)
        with Image.open(out) as result:
            assert result.size == (600, 400)


class TestProcessVideo:
    async def test_raises_when_output_hits_cap(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = tmp_path / "in.mp4"
        source.write_bytes(b"stub")
        out = tmp_path / "out.mp4"

        command: tuple[object, ...] = ()

        async def _fake_exec(*args: object, **_kwargs: object) -> AsyncMock:
            nonlocal command
            command = args
            out.write_bytes(b"x" * 2048)
            proc = AsyncMock()
            proc.communicate.return_value = (b"", b"")
            proc.returncode = 0
            return proc

        monkeypatch.setattr(
            "app.logic.media_upgrade.processing._MAX_OUTPUT_BYTES", 1024
        )
        monkeypatch.setattr(
            "app.logic.media_upgrade.processing._detect_hdr", lambda _: False
        )
        monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
        with pytest.raises(RuntimeError, match="cap"):
            await process_video(source, out)
        input_index = command.index("-i")
        assert command.count("-threads:v") == 2
        thread_indexes = [
            i for i, argument in enumerate(command) if argument == "-threads:v"
        ]
        assert thread_indexes[0] < input_index < thread_indexes[1]
        assert all(command[i + 1] == _VIDEO_THREADS for i in thread_indexes)
        filter_threads_index = command.index("-filter_threads")
        assert filter_threads_index < input_index
        assert command[filter_threads_index + 1] == _VIDEO_THREADS
