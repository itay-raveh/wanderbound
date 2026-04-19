"""Perceptual hashing and bipartite matching for media upgrade.

Matches compressed Polarsteps media (photos and videos) to Google Photos
originals using perceptual hashing (pHash) and the Hungarian algorithm
for optimal bipartite assignment.
"""

import dataclasses
import logging
import subprocess
from datetime import datetime
from io import BytesIO
from pathlib import Path

import imagehash
import numpy as np
import pillow_heif  # noqa: F401 - registers HEIC plugin for Pillow
from PIL import Image
from pydantic import BaseModel
from scipy.optimize import linear_sum_assignment

from app.logic.layout.media import is_video
from app.models.google_photos import GoogleMediaId, MediaFilename
from app.services.google_photos import PickedMediaItem

logger = logging.getLogger(__name__)

# Hamming distance threshold for accepting a match.
MATCH_THRESHOLD = 12

# Skip cross-step fallback if the matrix exceeds this size.
_FALLBACK_MAX_DIMENSION = 100

type LocalHash = imagehash.ImageHash | list[imagehash.ImageHash]


@dataclasses.dataclass(slots=True)
class HashedMedia:
    """A media item with its perceptual hash, ready for matching.

    Used on both sides of the matching problem: ``key`` is either
    a local filename or a Google Photos media ID.
    """

    key: str
    hash: imagehash.ImageHash | list[imagehash.ImageHash]
    is_video: bool


class MatchResult(BaseModel):
    local_name: MediaFilename
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
# Video frame hashing
# ---------------------------------------------------------------------------

_VIDEO_SAMPLE_POINTS = (0.10, 0.30, 0.50, 0.70)
_FFPROBE_TIMEOUT = 30
_FFMPEG_FRAME_TIMEOUT = 30


def _video_duration_sync(path: Path) -> float:
    """Get video duration via ffprobe (synchronous)."""
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=_FFPROBE_TIMEOUT,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        logger.debug("Could not parse duration for %s, defaulting to 2s", path.name)
        return 2.0


def extract_video_frame_hashes(path: Path) -> list[imagehash.ImageHash]:
    """Extract frames at 10/30/50/70% of duration and compute pHash for each."""
    duration = _video_duration_sync(path)
    hashes: list[imagehash.ImageHash] = []
    for pct in _VIDEO_SAMPLE_POINTS:
        ts = duration * pct
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                str(ts),
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "png",
                "-",
            ],
            capture_output=True,
            check=True,
            timeout=_FFMPEG_FRAME_TIMEOUT,
        )
        with Image.open(BytesIO(result.stdout)) as img:
            hashes.append(compute_phash(img))
    return hashes


# ---------------------------------------------------------------------------
# Cost matrix and Hungarian matching
# ---------------------------------------------------------------------------

_CROSS_TYPE_COST = MATCH_THRESHOLD + 1


def _pairwise_distance(a: LocalHash, b: LocalHash) -> int:
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


def match_across_windows(
    windows: list[StepWindow],
    google_by_window: dict[int, list[PickedMediaItem]],
    media_names: list[MediaFilename],
    local_hashes: dict[MediaFilename, LocalHash],
    candidate_hashes: dict[GoogleMediaId, imagehash.ImageHash],
) -> tuple[list[MatchResult], set[MediaFilename], set[GoogleMediaId]]:
    """Run Hungarian matching within each time window."""
    all_matches: list[MatchResult] = []
    matched_locals: set[MediaFilename] = set()
    matched_candidates: set[GoogleMediaId] = set()

    for window in windows:
        window_items = google_by_window[window.step_id]
        hashed_locals = [
            HashedMedia(key=n, hash=local_hashes[n], is_video=is_video(n))
            for n in media_names
            if n in local_hashes and n not in matched_locals
        ]
        hashed_cands = [
            HashedMedia(
                key=item.id,
                hash=candidate_hashes[item.id],
                is_video=item.type == "VIDEO",
            )
            for item in window_items
            if item.id in candidate_hashes and item.id not in matched_candidates
        ]
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
    matched_locals: set[MediaFilename],
    matched_candidates: set[GoogleMediaId],
    media_names: list[MediaFilename],
    local_hashes: dict[MediaFilename, LocalHash],
    google_items: list[PickedMediaItem],
    candidate_hashes: dict[GoogleMediaId, imagehash.ImageHash],
) -> None:
    """Try matching remaining unmatched media across all windows."""
    hashed_locals = [
        HashedMedia(key=n, hash=local_hashes[n], is_video=is_video(n))
        for n in media_names
        if n in local_hashes and n not in matched_locals
    ]
    hashed_cands = [
        HashedMedia(
            key=item.id,
            hash=candidate_hashes[item.id],
            is_video=item.type == "VIDEO",
        )
        for item in google_items
        if item.id in candidate_hashes and item.id not in matched_candidates
    ]

    if (
        hashed_locals
        and hashed_cands
        and len(hashed_locals) <= _FALLBACK_MAX_DIMENSION
        and len(hashed_cands) <= _FALLBACK_MAX_DIMENSION
    ):
        all_matches.extend(match_within_window(hashed_locals, hashed_cands))
