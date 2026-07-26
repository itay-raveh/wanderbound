"""Storage for source panorama files."""

from __future__ import annotations

import shutil
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, UnidentifiedImageError

if TYPE_CHECKING:
    from app.models.album_media import PanoramaConfig

_PANORAMAS_DIRECTORY = Path(".panoramas")
_ORIGINALS_DIRECTORY = Path(".panoramas") / "originals"
_PREVIEW_DIRECTORY = _PANORAMAS_DIRECTORY / "preview"
_RENDERED_DIRECTORY = _PANORAMAS_DIRECTORY / "rendered"
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


def panorama_original_path(album_dir: Path, original_path: str | None) -> Path | None:
    if original_path is None:
        return None
    candidate = (album_dir / original_path).resolve()
    panoramas = (album_dir / _PANORAMAS_DIRECTORY).resolve()
    try:
        candidate.relative_to(panoramas)
    except ValueError:
        return None
    return candidate


def panorama_asset_paths(
    album_dir: Path,
    media_name: str,
    panorama: PanoramaConfig | None,
) -> list[Path]:
    stem = Path(media_name).stem
    candidates: list[Path] = []
    original = panorama_original_path(
        album_dir, panorama.original_path if panorama else None
    )
    if original is not None:
        candidates.append(original)
    originals = album_dir / _ORIGINALS_DIRECTORY
    if originals.exists():
        candidates.extend(originals.glob(f"{stem}.*"))
    preview = album_dir / _PREVIEW_DIRECTORY
    if preview.exists():
        candidates.extend(preview.glob(f"{stem}.*"))
        candidates.append(preview / stem)
    candidates.append(album_dir / _RENDERED_DIRECTORY / stem)
    return list(dict.fromkeys(path for path in candidates if path.exists()))


def remove_panorama_assets(
    album_dir: Path,
    media_name: str,
    panorama: PanoramaConfig | None,
) -> None:
    """Remove only derived assets belonging to one media item."""
    for path in panorama_asset_paths(album_dir, media_name, panorama):
        if path.is_dir():
            with suppress(FileNotFoundError):
                shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
