import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import get_settings
from app.logic.upload import (
    TripMeta,
    _safe_extract,
    extract_and_scan,
    scan_user_folder,
)


def _jpeg_bytes(width: int = 10, height: int = 10) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height)).save(buf, "JPEG")
    return buf.getvalue()


_DEFAULT_JPEG = _jpeg_bytes()


def _mp4_bytes() -> bytes:
    header = bytearray(32)
    header[0:4] = (32).to_bytes(4, "big")  # box size
    header[4:8] = b"ftyp"
    header[8:12] = b"isom"
    return bytes(header)


def _make_zip(**entries: bytes) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf


def _user_json(**overrides: str | int | bool) -> bytes:
    data: dict[str, str | int | bool] = {
        "id": 1,
        "first_name": "Test",
        "last_name": "User",
        "locale": "en_US",
        "unit_is_km": True,
        "temperature_is_celsius": True,
    }
    data.update(overrides)
    return json.dumps(data).encode()


def _trip_json(
    *,
    trip_id: int = 100,
    step_ids: tuple[int, ...] = (1,),
) -> bytes:
    steps = [
        {
            "id": sid,
            "display_name": f"Step {sid}",
            "display_slug": f"step-{sid}",
            "description": "",
            "start_time": 1_700_000_000.0 + sid,
            "timezone_id": "UTC",
            "location": {
                "name": "Place",
                "detail": "",
                "country_code": "us",
                "lat": 0.0,
                "lon": 0.0,
            },
        }
        for sid in step_ids
    ]
    return json.dumps(
        {
            "id": trip_id,
            "slug": "my-trip",
            "name": "My Trip",
            "summary": "",
            "cover_photo_path": "https://example.com/cover.jpg",
            "step_count": len(steps),
            "all_steps": steps,
        }
    ).encode()


class TestSafeExtract:
    def test_rejects_too_many_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.logic.upload._MAX_FILES", 2)
        buf = _make_zip(
            **{
                "a.jpg": _DEFAULT_JPEG,
                "b.jpg": _DEFAULT_JPEG,
                "c.jpg": _DEFAULT_JPEG,
            }
        )
        with pytest.raises(zipfile.BadZipFile, match="too many files"):
            _safe_extract(buf, tmp_path)

    def test_rejects_symlinks(self, tmp_path: Path) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            info = zipfile.ZipInfo("link.jpg")
            # Unix symlink attribute (0xA in the top nibble of external_attr)
            info.external_attr = 0xA0000000
            zf.writestr(info, b"target")
        buf.seek(0)
        with pytest.raises(zipfile.BadZipFile, match="Symlink not allowed"):
            _safe_extract(buf, tmp_path)

    def test_rejects_path_traversal(self, tmp_path: Path) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../etc/passwd", _DEFAULT_JPEG)
        buf.seek(0)
        with pytest.raises(zipfile.BadZipFile, match="Path traversal"):
            _safe_extract(buf, tmp_path)

    def test_rejects_exceeding_size_limit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.logic.upload._MAX_TOTAL_BYTES", 100)
        big_jpeg = _jpeg_bytes(200, 200)
        buf = _make_zip(**{"big.jpg": big_jpeg})
        with pytest.raises(zipfile.BadZipFile, match="exceeds limit"):
            _safe_extract(buf, tmp_path)

    def test_rejects_disallowed_mime_type(self, tmp_path: Path) -> None:
        # A PNG file has a recognizable MIME type that is NOT in the allow list
        png_buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(png_buf, "PNG")
        buf = _make_zip(**{"image.png": png_buf.getvalue()})
        with pytest.raises(zipfile.BadZipFile, match="Disallowed file type"):
            _safe_extract(buf, tmp_path)

    def test_rejects_executable(self, tmp_path: Path) -> None:
        # ELF magic bytes → application/x-executable or similar
        elf_header = b"\x7fELF" + b"\x00" * 100
        buf = _make_zip(**{"malware.bin": elf_header})
        with pytest.raises(zipfile.BadZipFile, match="Disallowed file type"):
            _safe_extract(buf, tmp_path)

    def test_cumulative_size_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Set limit just under 2x the JPEG size so second file pushes it over
        monkeypatch.setattr(
            "app.logic.upload._MAX_TOTAL_BYTES", len(_DEFAULT_JPEG) + 10
        )
        buf = _make_zip(**{"a.jpg": _DEFAULT_JPEG, "b.jpg": _DEFAULT_JPEG})
        with pytest.raises(zipfile.BadZipFile, match="exceeds limit"):
            _safe_extract(buf, tmp_path)


class TestScanUserFolder:
    def test_parses_user_and_trips(self, tmp_path: Path) -> None:
        (tmp_path / "user").mkdir()
        (tmp_path / "user" / "user.json").write_bytes(_user_json())
        trip_dir = tmp_path / "trip" / "trip-100"
        trip_dir.mkdir(parents=True)
        (trip_dir / "trip.json").write_bytes(_trip_json(trip_id=100, step_ids=(1, 2)))

        ps_user, trips = scan_user_folder(tmp_path)
        assert ps_user.first_name == "Test"
        assert len(trips) == 1
        assert trips[0].step_count == 2
        assert trips[0].country_codes == ["us"]

    def test_missing_user_json_raises(self, tmp_path: Path) -> None:
        (tmp_path / "trip" / "t1").mkdir(parents=True)
        (tmp_path / "trip" / "t1" / "trip.json").write_bytes(_trip_json())
        with pytest.raises(FileNotFoundError):
            scan_user_folder(tmp_path)


class TestExtractAndScan:
    @pytest.fixture(autouse=True)
    def _mock_settings(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
        (tmp_path / "users").mkdir(exist_ok=True)

    def _build_valid_zip(
        self,
        *,
        user_overrides: dict | None = None,
        trip_count: int = 1,
    ) -> io.BytesIO:
        entries: dict[str, bytes] = {}
        entries["user/user.json"] = _user_json(**(user_overrides or {}))
        for i in range(trip_count):
            tid = 100 + i
            trip_dir = f"trip/trip-{tid}"
            entries[f"{trip_dir}/trip.json"] = _trip_json(trip_id=tid, step_ids=(1, 2))
        return _make_zip(**entries)

    def test_success(self) -> None:
        buf = self._build_valid_zip(trip_count=2)
        folder, ps_user, trips = extract_and_scan(buf)

        try:
            assert ps_user.first_name == "Test"
            assert len(trips) == 2
            for trip in trips:
                assert isinstance(trip, TripMeta)
                assert trip.step_count == 2
                assert trip.country_codes == ["us"]
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_fail_missing_user_json(self) -> None:
        buf = _make_zip(**{"trip/t1/trip.json": _trip_json()})
        with pytest.raises(FileNotFoundError):
            extract_and_scan(buf)

    def test_cleanup_on_failure(self, tmp_path: Path) -> None:
        buf = _make_zip(**{"trip/t1/trip.json": _trip_json()})

        dirs_before = set(tmp_path.iterdir())
        with pytest.raises(FileNotFoundError):
            extract_and_scan(buf)
        dirs_after = set(tmp_path.iterdir())

        assert dirs_after == dirs_before

    def test_fail_on_invalid_zip(self) -> None:
        buf = io.BytesIO(b"not a zip at all")
        with pytest.raises(zipfile.BadZipFile):
            extract_and_scan(buf)
