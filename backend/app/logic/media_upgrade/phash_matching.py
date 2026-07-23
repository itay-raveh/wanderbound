"""Perceptual hashing and bipartite matching for media upgrade.

Matches compressed Polarsteps media (photos and videos) to Google Photos
originals using perceptual hashing (pHash) and the Hungarian algorithm
for optimal bipartite assignment.
"""

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import imagehash
import numpy as np
import pillow_heif  # noqa: F401 - registers HEIC plugin for Pillow
from pydantic import BaseModel

if TYPE_CHECKING:
    from PIL import Image
from scipy.optimize import linear_sum_assignment

from app.logic.layout.media import MediaName, is_video, open_oriented
from app.models.google_photos import GoogleMediaId, PickedMediaItem

# Hamming distance threshold for accepting a pHash match.
# pHash produces a 64-bit hash; distance 0 = identical, 64 = maximally different.
# We compare Polarsteps exports (heavy JPEG, ~1024-2048px) against Google Photos
# thumbnails (400px, separate compression pipeline). Both derive from the same
# original but go through independent lossy pipelines, which typically introduces
# 8-12 bits of hash variance. 12 sits at the upper end of "same image, different
# compression" and below "different image" territory (~15+).
MATCH_THRESHOLD = 12

# Skip cross-step fallback if the matrix exceeds this size.
_FALLBACK_MAX_DIMENSION = 100

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


class StepWindow(BaseModel):
    step_id: int
    start: float  # unix timestamp
    end: float  # unix timestamp (includes overlap margin)

    def contains(self, timestamp: float) -> bool:
        return self.start <= timestamp < self.end


# ---------------------------------------------------------------------------
# Time-window bucketing
# ---------------------------------------------------------------------------

_OVERLAP_MARGIN = 24 * 60 * 60  # 24 hours


def build_step_windows(
    step_timestamps: list[float],
    step_ids: list[int],
) -> list[StepWindow]:
    """Build time windows for each step.

    Each window runs from the step's start_time to the next step's start_time
    (or +24h for the last step), padded by an overlap margin on both sides so
    neighbor windows share ground.
    """
    windows: list[StepWindow] = []
    for i, (ts, sid) in enumerate(zip(step_timestamps, step_ids, strict=True)):
        end = step_timestamps[i + 1] if i + 1 < len(step_timestamps) else ts + 86400
        windows.append(
            StepWindow(
                step_id=sid,
                start=ts - _OVERLAP_MARGIN,
                end=end + _OVERLAP_MARGIN,
            ),
        )
    return windows


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
# Cost matrix and Hungarian matching
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
) -> list[list[int]]:
    """Build a distance matrix. Cross-type pairs get infinite cost."""
    matrix: list[list[int]] = []
    for loc in local_media:
        row: list[int] = []
        for cand in candidate_media:
            if loc.is_video != cand.is_video:
                row.append(_CROSS_TYPE_COST)
            else:
                row.append(_pairwise_distance(loc.hash, cand.hash))
        matrix.append(row)
    return matrix


def _thresholded_assignment(
    cost: np.ndarray,
    threshold: int,
) -> tuple[np.ndarray, np.ndarray]:
    if cost.size == 0:
        return np.array([], dtype=int), np.array([], dtype=int)

    local_count, candidate_count = cost.shape
    unmatched_cost = local_count * threshold + 1
    invalid_cost = unmatched_cost * (local_count + 1)
    assignment = np.full(
        (local_count, candidate_count + local_count),
        invalid_cost,
        dtype=np.int64,
    )
    valid = cost <= threshold
    assignment[:, :candidate_count][valid] = cost[valid]
    assignment[np.arange(local_count), candidate_count + np.arange(local_count)] = (
        unmatched_cost
    )

    rows, columns = linear_sum_assignment(assignment)
    real = columns < candidate_count
    return rows[real], columns[real]


def match_within_window(
    local_media: list[HashedMedia],
    candidate_media: list[HashedMedia],
    threshold: int = MATCH_THRESHOLD,
) -> list[MatchResult]:
    return match_media_globally(local_media, candidate_media, threshold).matches


def match_media_globally(
    local_media: list[HashedMedia],
    candidate_media: list[HashedMedia],
    threshold: int = MATCH_THRESHOLD,
) -> MatchingOutcome:
    if not local_media or not candidate_media:
        return MatchingOutcome([], MatchingDiagnostics(0, 0))

    cost = np.asarray(build_cost_matrix(local_media, candidate_media), dtype=np.int16)
    same_type = np.equal.outer(
        [item.is_video for item in local_media],
        [item.is_video for item in candidate_media],
    )
    valid = same_type & (cost <= threshold)
    assignment_cost = np.where(valid, cost, threshold + 1)
    rows, columns = _thresholded_assignment(assignment_cost, threshold)
    matches = [
        MatchResult(
            local_name=local_media[row].key,
            google_id=candidate_media[column].key,
            distance=int(cost[row, column]),
        )
        for row, column in zip(rows, columns, strict=True)
    ]
    same_type_cost = np.where(same_type, cost, np.iinfo(np.int16).max)
    nearest = same_type_cost.min(axis=1)
    return MatchingOutcome(
        matches,
        MatchingDiagnostics(
            valid_edges=int(valid.sum()),
            nearest_13_to_15=int(((nearest >= 13) & (nearest <= 15)).sum()),
        ),
    )


# ---------------------------------------------------------------------------
# Full matching pipeline - helpers
# ---------------------------------------------------------------------------


def _parse_timestamp(create_time: str) -> float | None:
    """Parse an ISO 8601 timestamp to a Unix epoch float, or None on failure."""
    try:
        return datetime.fromisoformat(create_time).timestamp()
    except ValueError:
        return None


def bucket_by_window(
    google_items: list[PickedMediaItem],
    windows: list[StepWindow],
) -> dict[int, list[PickedMediaItem]]:
    """Assign Google Photos items to step windows by creation timestamp."""
    by_window: dict[int, list[PickedMediaItem]] = {w.step_id: [] for w in windows}
    for item in google_items:
        if (
            item.type == "VIDEO"
            and item.video_processing_status is not None
            and item.video_processing_status != "READY"
        ):
            continue
        ct = _parse_timestamp(item.create_time)
        if ct is None:
            continue
        for w in windows:
            if ct < w.start:
                break  # windows sorted by start; no later window can match
            if w.contains(ct):
                by_window[w.step_id].append(item)
    return by_window


def deduplicate_items(
    items: list[PickedMediaItem],
) -> list[PickedMediaItem]:
    """Remove duplicate items by ID, preserving order."""
    return list({item.id: item for item in items}.values())


def _hashed_locals(
    media_names: list[MediaName],
    local_hashes: dict[MediaName, MediaHash],
    matched_locals: set[MediaName],
) -> list[HashedMedia]:
    return [
        HashedMedia(key=n, hash=local_hashes[n], is_video=is_video(n))
        for n in media_names
        if n in local_hashes and n not in matched_locals
    ]


def _hashed_candidates(
    items: list[PickedMediaItem],
    candidate_hashes: dict[GoogleMediaId, imagehash.ImageHash],
    matched_candidates: set[GoogleMediaId],
) -> list[HashedMedia]:
    return [
        HashedMedia(
            key=item.id,
            hash=candidate_hashes[item.id],
            is_video=item.type == "VIDEO",
        )
        for item in items
        if item.id in candidate_hashes and item.id not in matched_candidates
    ]


def match_across_windows(
    windows: list[StepWindow],
    google_by_window: dict[int, list[PickedMediaItem]],
    media_names: list[MediaName],
    local_hashes: dict[MediaName, MediaHash],
    candidate_hashes: dict[GoogleMediaId, imagehash.ImageHash],
) -> tuple[list[MatchResult], set[MediaName], set[GoogleMediaId]]:
    """Run Hungarian matching within each time window."""
    all_matches: list[MatchResult] = []
    matched_locals: set[MediaName] = set()
    matched_candidates: set[GoogleMediaId] = set()

    for window in windows:
        hashed_locals = _hashed_locals(media_names, local_hashes, matched_locals)
        hashed_cands = _hashed_candidates(
            google_by_window[window.step_id], candidate_hashes, matched_candidates
        )
        if not hashed_locals or not hashed_cands:
            continue

        results = match_within_window(hashed_locals, hashed_cands)
        for r in results:
            all_matches.append(r)
            matched_locals.add(r.local_name)
            matched_candidates.add(r.google_id)

    return all_matches, matched_locals, matched_candidates


def cross_step_fallback(  # noqa: PLR0913
    all_matches: list[MatchResult],
    matched_locals: set[MediaName],
    matched_candidates: set[GoogleMediaId],
    media_names: list[MediaName],
    local_hashes: dict[MediaName, MediaHash],
    google_items: list[PickedMediaItem],
    candidate_hashes: dict[GoogleMediaId, imagehash.ImageHash],
) -> None:
    """Try matching remaining unmatched media across all windows."""
    hashed_locals = _hashed_locals(media_names, local_hashes, matched_locals)
    hashed_cands = _hashed_candidates(
        google_items, candidate_hashes, matched_candidates
    )

    if (
        hashed_locals
        and hashed_cands
        and len(hashed_locals) <= _FALLBACK_MAX_DIMENSION
        and len(hashed_cands) <= _FALLBACK_MAX_DIMENSION
    ):
        all_matches.extend(match_within_window(hashed_locals, hashed_cands))
