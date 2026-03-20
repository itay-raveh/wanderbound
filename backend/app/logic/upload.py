import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import BinaryIO

from pydantic import BaseModel

from app.core.config import settings
from app.models.polarsteps import CountryCode, PSTrip
from app.models.user import PSUser, User

logger = logging.getLogger(__name__)

# Python 3.12+ zipfile already detects quoted-overlap zip bombs (CVE-2024-0450).
# These limits guard against decompression bombs and excessive file counts.
_MAX_FILES = 50_000
_MAX_TOTAL_BYTES = 20 * 1024 * 1024 * 1024  # 20 GB uncompressed


def _safe_extract(file: BinaryIO, dest: Path) -> None:
    """Extract ZIP with path-traversal, symlink, size, and file-count checks."""
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
            try:
                (dest / info.filename).resolve().relative_to(resolved_dest)
            except ValueError:
                msg = f"Path traversal detected: {info.filename}"
                raise zipfile.BadZipFile(msg) from None

            total += info.file_size
            if total > _MAX_TOTAL_BYTES:
                msg = "ZIP uncompressed size exceeds limit"
                raise zipfile.BadZipFile(msg)

        zf.extractall(dest)


class TripMeta(BaseModel):
    id: str
    title: str
    step_count: int
    country_codes: list[CountryCode]


class UploadResult(BaseModel):
    user: User
    trips: list[TripMeta]


def extract_and_scan(file: BinaryIO) -> tuple[Path, PSUser, list[TripMeta]]:
    """Extract ZIP to temp folder, parse user and trips (blocking I/O)."""
    folder = Path(tempfile.mkdtemp(dir=settings.USERS_FOLDER))
    try:
        _safe_extract(file, folder)
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
                        {s.location.country_code for s in trip.all_steps}
                    ),
                )
            )
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return folder, ps_user, trips
