from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

import imagehash
import structlog
from joblib import Parallel, delayed

from app.core.resources import detect_cpu_count
from app.logic.layout.media import is_video

from .phash_matching import compute_phash_from_path

if TYPE_CHECKING:
    from joblib.memory import MemorizedFunc

logger = structlog.get_logger(__name__)

_HASH_WORKERS = min(2, detect_cpu_count())


def serialize_media_hash(media_hash: imagehash.ImageHash) -> list[str]:
    return [str(media_hash)]


def deserialize_media_hash(value: list[str]) -> imagehash.ImageHash:
    if len(value) != 1:
        raise ValueError("A photo must have exactly one perceptual hash")
    if not isinstance(value[0], str) or len(value[0]) != 16:
        raise ValueError("Perceptual hashes must be 64-bit hexadecimal strings")
    try:
        return imagehash.hex_to_hash(value[0])
    except ValueError as exc:
        raise ValueError(
            "Perceptual hashes must be 64-bit hexadecimal strings"
        ) from exc


def compute_media_hash(path: Path) -> imagehash.ImageHash:
    return compute_phash_from_path(path)


def compute_serialized_media_hash(path: Path) -> list[str]:
    return serialize_media_hash(compute_media_hash(path))


def _hash_path(
    path: Path, cached_hash: MemorizedFunc | None = None
) -> tuple[str, list[str]] | None:
    if is_video(path.name):
        return None
    try:
        if cached_hash is None:
            hashes = compute_serialized_media_hash(path)
        else:
            stat = path.stat()
            hashes = serialize_media_hash(
                cached_hash(
                    path,
                    stat.st_dev,
                    stat.st_ino,
                    stat.st_size,
                    stat.st_mtime_ns,
                )
            )
    except OSError, SyntaxError, ValueError:
        logger.warning("media_hash.compute_failed", media_name=path.name)
        return None
    else:
        return path.name, hashes


def try_compute_serialized_media_hash(path: Path) -> list[str] | None:
    result = _hash_path(path)
    return result[1] if result is not None else None


def compute_serialized_media_hashes(
    paths: Iterable[Path],
    *,
    workers: int | None = None,
    cached_hash: MemorizedFunc | None = None,
) -> dict[str, list[str]]:
    results = Parallel(
        n_jobs=_HASH_WORKERS if workers is None else workers,
        prefer="threads",
        return_as="generator_unordered",
        pre_dispatch="n_jobs",
    )(delayed(_hash_path)(path, cached_hash) for path in paths)
    return dict(result for result in results if result is not None)
