"""Storage for source panorama files."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image, UnidentifiedImageError

_ORIGINALS_DIRECTORY = Path(".panoramas") / "originals"
_FORMAT_SUFFIXES = {
    "AVIF": ".avif",
    "HEIF": ".heic",
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}


def preserve_panorama_original(raw: Path, album_dir: Path, media_name: str) -> Path:
    """Copy a candidate source image beneath the album's panorama directory."""
    target = album_dir / _ORIGINALS_DIRECTORY / f"{Path(media_name).stem}{_suffix(raw)}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw, target)
    return target


def _suffix(raw: Path) -> str:
    try:
        with Image.open(raw) as image:
            detected = _FORMAT_SUFFIXES.get(image.format or "")
    except UnidentifiedImageError, OSError, SyntaxError:
        detected = None
    return detected or raw.suffix.lower() or ".jpg"
