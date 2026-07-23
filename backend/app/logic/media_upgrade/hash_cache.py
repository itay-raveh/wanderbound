"""Persistent perceptual-hash cache for local album media."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from joblib import Memory

if TYPE_CHECKING:
    from joblib.memory import MemorizedFunc

from app.core.config import get_settings
from app.logic.layout.media import is_video

from .phash_matching import MediaHash, compute_phash_from_path
from .processing import extract_video_frame_hashes

_CACHE_DIR = ".media-hash-cache"


def _compute_local_hash(
    path: Path,
    _size: int,
    _mtime_ns: int,
) -> MediaHash:
    if is_video(path.name):
        return extract_video_frame_hashes(path)
    return compute_phash_from_path(path)


def album_hash_memory(album_dir: Path) -> Memory:
    users_folder = get_settings().USERS_FOLDER
    try:
        user_dir = users_folder / album_dir.relative_to(users_folder).parts[0]
    except IndexError, ValueError:
        user_dir = album_dir
    cache_dir = user_dir / _CACHE_DIR / album_dir.name
    return Memory(cache_dir, verbose=0)


def local_hash_cache(
    album_dir: Path,
    cache_validation_callback: Callable[[dict[str, object]], bool] | None = None,
) -> MemorizedFunc:
    return album_hash_memory(album_dir).cache(
        _compute_local_hash,
        cache_validation_callback=cache_validation_callback,
    )
