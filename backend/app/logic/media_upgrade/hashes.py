from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

import imagehash
import structlog
from joblib import Parallel, delayed

from app.core.resources import detect_cpu_count
from app.logic.layout.media import is_video

from .phash_matching import MediaHash, compute_phash_from_path

if TYPE_CHECKING:
    from joblib.memory import MemorizedFunc

logger = structlog.get_logger(__name__)

_HASH_WORKERS = min(2, detect_cpu_count())


def serialize_media_hash(media_hash: MediaHash) -> list[str]:
    hashes = media_hash if isinstance(media_hash, list) else [media_hash]
    return [str(value) for value in hashes]


def deserialize_media_hash(value: list[str]) -> MediaHash:
    if not value or any(not isinstance(item, str) or len(item) != 16 for item in value):
        raise ValueError("Perceptual hashes must be 64-bit hexadecimal strings")
    try:
        hashes = [imagehash.hex_to_hash(item) for item in value]
    except ValueError as exc:
        raise ValueError(
            "Perceptual hashes must be 64-bit hexadecimal strings"
        ) from exc
    return hashes if len(hashes) != 1 else hashes[0]


def compute_media_hash(path: Path) -> MediaHash:
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
