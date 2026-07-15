import shutil
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

import puremagic

from app.core.config import get_settings
from app.models.polarsteps import PSTrip
from app.models.upload import TripMeta, UploadResult
from app.models.user import PSUser

__all__ = ["TripMeta", "UploadResult", "extract_and_scan", "scan_user_folder"]

# Python 3.12+ zipfile already detects quoted-overlap zip bombs (CVE-2024-0450).
# These limits guard against decompression bombs and excessive file counts.
_MAX_FILES = 50_000
_MAX_TOTAL_BYTES = 20 * 1024 * 1024 * 1024  # 20 GB uncompressed

_INNER_MIMES = {"image/jpeg", "video/mp4", "application/json", "text/plain"}
_HEADER_BYTES = 2048
_PROGRESS_CHUNK_BYTES = 16 * 1024 * 1024

ProgressCallback = Callable[[tuple[int, int]], None]


def _detect_mime(data: bytes) -> str | None:
    """Return MIME type from magic bytes, or None if unrecognizable."""
    try:
        return puremagic.from_string(data, mime=True)
    except puremagic.PureError:
        return None


def _check_zip_mime(file: BinaryIO) -> None:
    """Validate the file is a ZIP archive."""
    if not zipfile.is_zipfile(file):
        raise zipfile.BadZipFile("File is not a ZIP archive")
    file.seek(0)


def _extract_entries(
    zf: zipfile.ZipFile,
    entries: list[zipfile.ZipInfo],
    dest: Path,
    total: int,
    progress: ProgressCallback | None,
) -> None:
    done = 0
    reported = 0
    interval = max(1, min(_PROGRESS_CHUNK_BYTES, max(1, total // 100)))
    if progress is not None:
        progress((0, total))

    def advance(amount: int) -> None:
        nonlocal done, reported
        done += amount
        if progress is not None and (done - reported >= interval or done >= total):
            reported = done
            progress((done, total))

    for info in entries:
        target = dest / info.filename
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        with zf.open(info) as src:
            header = src.read(_HEADER_BYTES)
            mime = _detect_mime(header)
            if mime not in _INNER_MIMES:
                raise zipfile.BadZipFile(
                    f"Disallowed file type: {info.filename} ({mime})"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as out:
                out.write(header)
                advance(len(header))
                while chunk := src.read(_PROGRESS_CHUNK_BYTES):
                    out.write(chunk)
                    advance(len(chunk))


def _safe_extract(
    file: BinaryIO, dest: Path, progress: ProgressCallback | None = None
) -> None:
    """Extract ZIP with MIME, path-traversal, symlink, size, and file-count checks."""
    _check_zip_mime(file)
    with zipfile.ZipFile(file) as zf:
        entries = zf.infolist()
        if len(entries) > _MAX_FILES:
            msg = f"ZIP contains too many files ({len(entries)})"
            raise zipfile.BadZipFile(msg)

        resolved_dest = dest.resolve()
        total = 0
        for info in entries:
            # Reject symlinks (external_attr high byte 0xA = symlink on Unix)
            if (info.external_attr >> 28) == 0xA:
                msg = f"Symlink not allowed: {info.filename}"
                raise zipfile.BadZipFile(msg)

            # Path traversal check
            target = (dest / info.filename).resolve()
            try:
                target.relative_to(resolved_dest)
            except ValueError:
                msg = f"Path traversal detected: {info.filename}"
                raise zipfile.BadZipFile(msg) from None

            total += info.file_size
            if total > _MAX_TOTAL_BYTES:
                msg = "ZIP uncompressed size exceeds limit"
                raise zipfile.BadZipFile(msg)

        _extract_entries(zf, entries, dest, total, progress)


def scan_user_folder(folder: Path) -> tuple[PSUser, list[TripMeta]]:
    """Parse user.json and enumerate trips from an extracted data folder."""
    user_json = (folder / "user" / "user.json").read_bytes()
    ps_user = PSUser.model_validate_json(user_json)

    trip_dir = folder / "trip"
    trips: list[TripMeta] = []
    for td in sorted(trip_dir.iterdir()):
        trip = PSTrip.from_trip_dir(td)
        trips.append(
            TripMeta(
                id=td.name,
                title=trip.title,
                step_count=trip.step_count,
                country_codes=list(
                    {s.location.country_code for s in trip.all_steps} - {"00"}
                ),
            )
        )
    return ps_user, trips


def extract_and_scan(file: BinaryIO) -> tuple[Path, PSUser, list[TripMeta]]:
    """Extract ZIP to temp folder, parse user and trips (blocking I/O)."""
    folder = Path(tempfile.mkdtemp(dir=get_settings().USERS_FOLDER))
    try:
        _safe_extract(file, folder)
        ps_user, trips = scan_user_folder(folder)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return folder, ps_user, trips
