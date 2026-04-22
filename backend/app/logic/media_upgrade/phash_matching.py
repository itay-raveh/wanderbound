"""Perceptual hashing and bipartite matching for media upgrade.

Matches compressed Polarsteps media (photos and videos) to Google Photos
originals using perceptual hashing (pHash) and the Hungarian algorithm
for optimal bipartite assignment.
"""

import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import NamedTuple

import imagehash
import numpy as np
import pillow_heif  # noqa: F401 - registers HEIC plugin for Pillow
from PIL import Image
from pydantic import BaseModel
from scipy.optimize import linear_sum_assignment

from app.logic.layout.media import MediaName, is_video
from app.models.google_photos import GoogleMediaId, PickedMediaItem

logger = logging.getLogger(__name__)

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


class StepWindow(BaseModel):
    step_id: int
    start: float  # unix timestamp
    end: float  # unix timestamp (includes overlap margin)

    def contains(self, timestamp: float) -> bool:
        return self.start <= timestamp < self.end


# ---------------------------------------------------------------------------
# Time-window bucketing
# ---------------------------------------------------------------------------

# Buffer added to each step window boundary. Polarsteps step timestamps can
# land anywhere within a multi-day step, so windows are primarily defined by
# adjacent step starts. This margin catches photos with slight clock skew at
# the boundaries. Photos shared/received later (with download timestamps far
# from the original event) are handled by cross_step_fallback, which matches
# all remaining unmatched items globally regardless of time windows.
_OVERLAP_MARGIN = 30 * 60  # 30 minutes in seconds


def build_step_windows(
    step_timestamps: list[float],
    step_ids: list[int],
) -> list[StepWindow]:
    """Build time windows for each step.

    Each window runs from the step's start_time to the next step's start_time
    (or +24h for the last step), plus an overlap margin.
    """
    windows: list[StepWindow] = []
    for i, (ts, sid) in enumerate(zip(step_timestamps, step_ids, strict=True)):
        # First window extends backward to catch items with clock skew or
        # timezone offsets (e.g. photos taken just before departure).
        start = ts - _OVERLAP_MARGIN if i == 0 else ts
        end = step_timestamps[i + 1] if i + 1 < len(step_timestamps) else ts + 86400
        windows.append(StepWindow(step_id=sid, start=start, end=end + _OVERLAP_MARGIN))
    return windows


# ---------------------------------------------------------------------------
# Perceptual hashing
# ---------------------------------------------------------------------------


def compute_phash(image: Image.Image) -> imagehash.ImageHash:
    """Compute a 64-bit perceptual hash."""
    return imagehash.phash(image)


def compute_phash_from_path(path: Path) -> imagehash.ImageHash:
    with Image.open(path) as img:
        return compute_phash(img)


def compute_phash_from_bytes(data: bytes) -> imagehash.ImageHash:
    with Image.open(BytesIO(data)) as img:
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


def match_within_window(
    local_media: list[HashedMedia],
    candidate_media: list[HashedMedia],
    threshold: int = MATCH_THRESHOLD,
) -> list[MatchResult]:
    """Run Hungarian algorithm on a cost matrix, reject pairs above threshold."""
    if not local_media or not candidate_media:
        return []

    cost = np.array(build_cost_matrix(local_media, candidate_media))
    row_idx, col_idx = linear_sum_assignment(cost)

    results: list[MatchResult] = []
    for r, c in zip(row_idx, col_idx, strict=True):
        dist = int(cost[r, c])
        if dist <= threshold:
            results.append(
                MatchResult(
                    local_name=local_media[r].key,
                    google_id=candidate_media[c].key,
                    distance=dist,
                )
            )
    return results


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
