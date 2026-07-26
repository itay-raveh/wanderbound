"""Storage for source panorama files."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, UnidentifiedImageError

if TYPE_CHECKING:
    from app.models.album_media import PanoramaConfig

_PANORAMAS_DIRECTORY = Path(".panoramas")
_ORIGINALS_DIRECTORY = Path(".panoramas") / "originals"
_PREVIEW_DIRECTORY = _PANORAMAS_DIRECTORY / "preview"
_RENDERED_DIRECTORY = _PANORAMAS_DIRECTORY / "rendered"
MAX_RENDITIONS_PER_REVISION = 8
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


def remove_panorama_assets(
    album_dir: Path,
    media_name: str,
    panorama: PanoramaConfig | None,
) -> None:
    """Remove only derived assets belonging to one media item."""
    stem = Path(media_name).stem
    original = panorama_original_path(
        album_dir, panorama.original_path if panorama else None
    )
    if original is not None:
        original.unlink(missing_ok=True)
    originals = album_dir / _ORIGINALS_DIRECTORY
    if originals.exists():
        for candidate in originals.glob(f"{stem}.*"):
            candidate.unlink(missing_ok=True)
    preview = album_dir / _PREVIEW_DIRECTORY
    if preview.exists():
        for candidate in preview.glob(f"{stem}.*"):
            candidate.unlink(missing_ok=True)
        shutil.rmtree(preview / stem, ignore_errors=True)
    shutil.rmtree(album_dir / _RENDERED_DIRECTORY / stem, ignore_errors=True)


def remove_panorama_derivatives(album_dir: Path, media_name: str) -> None:
    stem = Path(media_name).stem
    preview = album_dir / _PREVIEW_DIRECTORY
    if preview.exists():
        for candidate in preview.glob(f"{stem}.*"):
            candidate.unlink(missing_ok=True)
        shutil.rmtree(preview / stem, ignore_errors=True)
    shutil.rmtree(album_dir / _RENDERED_DIRECTORY / stem, ignore_errors=True)


def remove_obsolete_render_revisions(
    album_dir: Path,
    media_name: str,
    keep_revision: int,
) -> None:
    rendered = album_dir / _RENDERED_DIRECTORY / Path(media_name).stem
    if not rendered.exists():
        return
    for revision in rendered.iterdir():
        if revision.is_dir() and revision.name != str(keep_revision):
            shutil.rmtree(revision, ignore_errors=True)


def prune_panorama_renditions(revision_dir: Path, keep: Path) -> None:
    renditions = sorted(
        (path for path in revision_dir.glob("*.jpg") if path != keep),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for rendition in renditions[MAX_RENDITIONS_PER_REVISION - 1 :]:
        rendition.unlink(missing_ok=True)
