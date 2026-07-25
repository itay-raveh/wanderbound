"""Match compressed local photos to Google Photos originals."""

from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import imagehash
import numpy as np
import pillow_heif  # noqa: F401 - registers HEIC plugin for Pillow
from pydantic import BaseModel

if TYPE_CHECKING:
    from PIL import Image
from scipy.sparse import coo_array
from scipy.sparse.csgraph import min_weight_full_bipartite_matching

from app.logic.layout.media import open_oriented
from app.models.google_photos import GoogleMediaId, PickedMediaItem

# Hamming distance threshold for accepting a pHash match.
# pHash produces a 64-bit hash; distance 0 = identical, 64 = maximally different.
# We compare Polarsteps exports (heavy JPEG, ~1024-2048px) against Google Photos
# thumbnails (400px, separate compression pipeline). Both derive from the same
# original but go through independent lossy pipelines, which typically introduces
# 8-12 bits of hash variance. 12 sits at the upper end of "same image, different
# compression" and below "different image" territory (~15+).
MATCH_THRESHOLD = 12


class HashedMedia(NamedTuple):
    key: str
    hash: imagehash.ImageHash


class MatchResult(BaseModel):
    local_name: str
    google_id: GoogleMediaId
    distance: int
    upgraded: bool = False


class MatchingDiagnostics(NamedTuple):
    valid_edges: int
    nearest_13_to_15: int


class MatchingOutcome(NamedTuple):
    matches: list[MatchResult]
    diagnostics: MatchingDiagnostics


# ---------------------------------------------------------------------------
# Perceptual hashing
# ---------------------------------------------------------------------------


def compute_phash(image: Image.Image) -> imagehash.ImageHash:
    """Compute a 64-bit perceptual hash."""
    return imagehash.phash(image)


def compute_phash_from_path(path: Path) -> imagehash.ImageHash:
    with open_oriented(path) as img:
        return compute_phash(img)


def compute_phash_from_bytes(data: bytes) -> imagehash.ImageHash:
    with open_oriented(BytesIO(data)) as img:
        return compute_phash(img)


# ---------------------------------------------------------------------------
# Cost matrix and optimal matching
# ---------------------------------------------------------------------------


def build_cost_matrix(
    local_media: list[HashedMedia],
    candidate_media: list[HashedMedia],
) -> np.ndarray:
    local_bits = np.stack([item.hash.hash.reshape(-1) for item in local_media])
    candidate_bits = np.stack([item.hash.hash.reshape(-1) for item in candidate_media])
    local_values = np.packbits(local_bits, axis=1).view(np.uint64).reshape(-1)
    candidate_values = np.packbits(candidate_bits, axis=1).view(np.uint64).reshape(-1)
    return np.bitwise_count(
        np.bitwise_xor(local_values[:, None], candidate_values[None, :])
    ).astype(np.int16)


def _thresholded_assignment(
    cost: np.ndarray,
    threshold: int,
) -> tuple[np.ndarray, np.ndarray]:
    if cost.size == 0:
        return np.array([], dtype=int), np.array([], dtype=int)

    local_count, candidate_count = cost.shape
    unmatched_cost = local_count * threshold + 1
    valid_rows, valid_columns = np.nonzero(cost <= threshold)
    dummy_rows = np.arange(local_count)
    dummy_columns = candidate_count + dummy_rows
    rows = np.concatenate((valid_rows, dummy_rows))
    columns = np.concatenate((valid_columns, dummy_columns))
    weights = np.concatenate(
        (
            cost[valid_rows, valid_columns].astype(np.int64) + 1,
            np.full(local_count, unmatched_cost + 1, dtype=np.int64),
        )
    )
    assignment = coo_array(
        (weights, (rows, columns)),
        shape=(local_count, candidate_count + local_count),
    ).tocsr()
    matched_rows, matched_columns = min_weight_full_bipartite_matching(assignment)
    real = matched_columns < candidate_count
    return matched_rows[real], matched_columns[real]


def match_media_globally(
    local_media: list[HashedMedia],
    candidate_media: list[HashedMedia],
    threshold: int = MATCH_THRESHOLD,
) -> MatchingOutcome:
    if not local_media or not candidate_media:
        return MatchingOutcome([], MatchingDiagnostics(0, 0))

    cost = build_cost_matrix(local_media, candidate_media)
    valid = cost <= threshold
    rows, columns = _thresholded_assignment(cost, threshold)
    matches = [
        MatchResult(
            local_name=local_media[row].key,
            google_id=candidate_media[column].key,
            distance=int(cost[row, column]),
        )
        for row, column in zip(rows, columns, strict=True)
    ]
    nearest = cost.min(axis=1)
    return MatchingOutcome(
        matches,
        MatchingDiagnostics(
            valid_edges=int(valid.sum()),
            nearest_13_to_15=int(((nearest >= 13) & (nearest <= 15)).sum()),
        ),
    )


# ---------------------------------------------------------------------------
# Candidate helpers
# ---------------------------------------------------------------------------


def deduplicate_items(
    items: list[PickedMediaItem],
) -> list[PickedMediaItem]:
    """Remove duplicate items by ID, preserving order."""
    return list({item.id: item for item in items}.values())
