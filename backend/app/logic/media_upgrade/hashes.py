from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import av
import imagehash
import structlog
from joblib import Parallel, delayed

from app.core.resources import detect_cpu_count
from app.logic.layout.media import is_video

from .phash_matching import MediaHash, compute_phash_from_path
from .processing import extract_video_frame_hashes

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
    if is_video(path.name):
        return extract_video_frame_hashes(path)
    return compute_phash_from_path(path)


def compute_serialized_media_hash(path: Path) -> list[str]:
    return serialize_media_hash(compute_media_hash(path))


def _hash_path(path: Path) -> tuple[str, list[str]] | None:
    try:
        return path.name, compute_serialized_media_hash(path)
    except OSError, SyntaxError, ValueError, av.FFmpegError:
        logger.warning("media_hash.compute_failed", media_name=path.name)
        return None


def try_compute_serialized_media_hash(path: Path) -> list[str] | None:
    result = _hash_path(path)
    return result[1] if result is not None else None


def compute_serialized_media_hashes(paths: Iterable[Path]) -> dict[str, list[str]]:
    results = Parallel(
        n_jobs=_HASH_WORKERS,
        prefer="threads",
        return_as="generator_unordered",
        pre_dispatch="n_jobs",
    )(delayed(_hash_path)(path) for path in paths)
    return dict(result for result in results if result is not None)
