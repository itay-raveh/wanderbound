"""Perceptual hashing and bipartite matching for media upgrade.

Matches compressed Polarsteps media (photos and videos) to Google Photos
originals using perceptual hashing (pHash) and optimal bipartite assignment.
"""

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

type MediaHash = imagehash.ImageHash | list[imagehash.ImageHash]


class HashedMedia(NamedTuple):
    """A media item with its perceptual hash, ready for matching.

    Used on both sides of the matching problem: ``key`` is either
    a local filename or a Google Photos media ID.
    """

    key: str
    hash: MediaHash
    is_video: bool


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

_CROSS_TYPE_COST = MATCH_THRESHOLD + 1


def _pairwise_distance(a: MediaHash, b: MediaHash) -> int:
    """Distance between two hashes. Multi-frame hashes use minimum distance."""
    # Flatten both sides to lists for uniform handling.
    frames_a = [a] if isinstance(a, imagehash.ImageHash) else a
    frames_b = [b] if isinstance(b, imagehash.ImageHash) else b
    if not frames_a or not frames_b:
        return _CROSS_TYPE_COST
    return min(int(fa - fb) for fa in frames_a for fb in frames_b)


def build_cost_matrix(
    local_media: list[HashedMedia],
    candidate_media: list[HashedMedia],
) -> np.ndarray:
    """Build a distance matrix. Cross-type pairs get infinite cost."""
    matrix = np.full(
        (len(local_media), len(candidate_media)),
        _CROSS_TYPE_COST,
        dtype=np.int16,
    )
    local_photo_entries = [
        (index, item.hash)
        for index, item in enumerate(local_media)
        if not item.is_video and isinstance(item.hash, imagehash.ImageHash)
    ]
    candidate_photo_entries = [
        (index, item.hash)
        for index, item in enumerate(candidate_media)
        if not item.is_video and isinstance(item.hash, imagehash.ImageHash)
    ]
    local_photos = [index for index, _ in local_photo_entries]
    candidate_photos = [index for index, _ in candidate_photo_entries]
    if local_photos and candidate_photos:
        local_bits = np.stack(
            [media_hash.hash.reshape(-1) for _, media_hash in local_photo_entries]
        )
        candidate_bits = np.stack(
            [media_hash.hash.reshape(-1) for _, media_hash in candidate_photo_entries]
        )
        local_values = np.packbits(local_bits, axis=1).view(np.uint64).reshape(-1)
        candidate_values = (
            np.packbits(candidate_bits, axis=1).view(np.uint64).reshape(-1)
        )
        matrix[np.ix_(local_photos, candidate_photos)] = np.bitwise_count(
            np.bitwise_xor(local_values[:, None], candidate_values[None, :])
        )

    local_photo_set = set(local_photos)
    candidate_photo_set = set(candidate_photos)
    for row, loc in enumerate(local_media):
        if loc.is_video:
            columns = (
                (column, cand)
                for column, cand in enumerate(candidate_media)
                if cand.is_video
            )
        elif row not in local_photo_set:
            columns = (
                (column, cand)
                for column, cand in enumerate(candidate_media)
                if not cand.is_video
            )
        else:
            columns = (
                (column, candidate_media[column])
                for column in range(len(candidate_media))
                if column not in candidate_photo_set
                and not candidate_media[column].is_video
            )
        for column, cand in columns:
            matrix[row, column] = _pairwise_distance(loc.hash, cand.hash)
    return matrix


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
    same_type = np.equal.outer(
        [item.is_video for item in local_media],
        [item.is_video for item in candidate_media],
    )
    cost[~same_type] = threshold + 1
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
    nearest = cost.min(
        axis=1,
        where=same_type,
        initial=np.iinfo(np.int16).max,
    )
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
