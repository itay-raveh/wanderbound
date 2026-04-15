"""Photo matching and upgrade logic.

Matches compressed Polarsteps photos to Google Photos originals using
perceptual hashing (pHash) and the Hungarian algorithm for optimal
bipartite assignment.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Literal

import imagehash
import numpy as np
import pillow_heif  # noqa: F401 - registers HEIC plugin for Pillow
from PIL import Image
from pydantic import BaseModel
from scipy.optimize import linear_sum_assignment

from app.logic.layout.media import Media, delete_thumbnails
from app.services.google_photos import PickedMediaItem, download_media_bytes

logger = logging.getLogger(__name__)

# Hamming distance threshold for accepting a match.
MATCH_THRESHOLD = 12

# Skip cross-step fallback if the matrix exceeds this size.
_FALLBACK_MAX_DIMENSION = 100

# Bounded concurrency for thumbnail downloads during matching.
_MATCH_DOWNLOAD_SEM = asyncio.Semaphore(5)

# Bounded concurrency for original downloads during replacement.
_REPLACE_DOWNLOAD_SEM = asyncio.Semaphore(5)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class StepWindow(BaseModel):
    step_id: int
    start: float  # unix timestamp
    end: float  # unix timestamp (includes overlap margin)

    def contains(self, timestamp: float) -> bool:
        return self.start <= timestamp < self.end


class MatchResult(BaseModel):
    local_name: str
    google_id: str
    distance: int


# SSE event types
class UpgradeMatching(BaseModel):
    type: Literal["matching"] = "matching"
    phase: str
    done: int
    total: int


class UpgradeDownloading(BaseModel):
    type: Literal["downloading"] = "downloading"
    done: int
    total: int


class UpgradeReplacing(BaseModel):
    type: Literal["replacing"] = "replacing"
    done: int
    total: int


class UpgradeMatchSummary(BaseModel):
    type: Literal["match_summary"] = "match_summary"
    total_photos: int
    matched: int
    unmatched: int
    matches: list[MatchResult]


class UpgradeDone(BaseModel):
    type: Literal["done"] = "done"
    replaced: int
    failed: int


class UpgradeError(BaseModel):
    type: Literal["error"] = "error"
    detail: str


UpgradeEvent = (
    UpgradeMatching
    | UpgradeDownloading
    | UpgradeReplacing
    | UpgradeMatchSummary
    | UpgradeDone
    | UpgradeError
)


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
        end = step_timestamps[i + 1] if i + 1 < len(step_timestamps) else ts + 86400
        windows.append(StepWindow(step_id=sid, start=ts, end=end + _OVERLAP_MARGIN))
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


def build_cost_matrix(
    local_hashes: list[imagehash.ImageHash],
    candidate_hashes: list[imagehash.ImageHash],
) -> list[list[int]]:
    """Build a Hamming distance matrix between local and candidate hashes."""
    return [[int(lh - ch) for ch in candidate_hashes] for lh in local_hashes]


def match_within_window(
    local_names: list[str],
    local_hashes: list[imagehash.ImageHash],
    candidate_ids: list[str],
    candidate_hashes: list[imagehash.ImageHash],
    threshold: int = MATCH_THRESHOLD,
) -> list[MatchResult]:
    """Run Hungarian algorithm on a cost matrix, reject pairs above threshold."""
    if not local_names or not candidate_ids:
        return []

    cost = np.array(build_cost_matrix(local_hashes, candidate_hashes))
    row_idx, col_idx = linear_sum_assignment(cost)

    results: list[MatchResult] = []
    for r, c in zip(row_idx, col_idx, strict=True):
        dist = int(cost[r, c])
        if dist <= threshold:
            results.append(
                MatchResult(
                    local_name=local_names[r],
                    google_id=candidate_ids[c],
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
        return datetime.fromisoformat(create_time).replace(tzinfo=UTC).timestamp()
    except ValueError, OSError:
        return None


def _bucket_by_window(
    google_items: list[PickedMediaItem],
    windows: list[StepWindow],
) -> dict[int, list[PickedMediaItem]]:
    """Assign Google Photos items to step windows by creation timestamp."""
    by_window: dict[int, list[PickedMediaItem]] = {w.step_id: [] for w in windows}
    for item in google_items:
        if item.type != "PHOTO":
            continue
        ct = _parse_timestamp(item.create_time)
        if ct is None:
            continue
        for w in windows:
            if w.contains(ct):
                by_window[w.step_id].append(item)
    return by_window


def _deduplicate_items(
    items: list[PickedMediaItem],
) -> list[PickedMediaItem]:
    """Remove duplicate items by ID, preserving order."""
    seen: set[str] = set()
    unique: list[PickedMediaItem] = []
    for item in items:
        if item.id not in seen:
            seen.add(item.id)
            unique.append(item)
    return unique


async def _hash_local_photos(
    album_dir: Path,
    photo_names: list[str],
) -> dict[str, imagehash.ImageHash]:
    """Compute perceptual hashes for local photo files."""
    hashes: dict[str, imagehash.ImageHash] = {}
    for name in photo_names:
        path = album_dir / name
        if not path.exists():
            continue
        try:
            h = await asyncio.to_thread(compute_phash_from_path, path)
        except OSError, SyntaxError:
            logger.warning("Failed to hash %s", name, exc_info=True)
        else:
            hashes[name] = h
    return hashes


async def _hash_candidates(
    items: list[PickedMediaItem],
    access_token: str,
) -> dict[str, imagehash.ImageHash]:
    """Download thumbnails and compute perceptual hashes for candidates."""
    hashes: dict[str, imagehash.ImageHash] = {}
    for item in items:
        try:
            async with _MATCH_DOWNLOAD_SEM:
                thumb_bytes = await download_media_bytes(
                    item.media_file.base_url, access_token, param="=w400"
                )
            h = await asyncio.to_thread(compute_phash_from_bytes, thumb_bytes)
        except OSError, SyntaxError:
            logger.warning(
                "Failed to download/hash thumbnail for %s",
                item.id,
                exc_info=True,
            )
        else:
            hashes[item.id] = h
    return hashes


# ---------------------------------------------------------------------------
# Full matching pipeline
# ---------------------------------------------------------------------------


async def run_matching(  # noqa: PLR0913
    album_dir: Path,
    photo_names: list[str],
    step_timestamps: list[float],
    step_ids: list[int],
    google_items: list[PickedMediaItem],
    access_token: str,
) -> AsyncIterator[UpgradeEvent]:
    """Run the full matching pipeline, yielding SSE events for progress.

    1. Hash local photos
    2. Bucket Google items into step windows
    3. Download thumbnails and hash them
    4. Hungarian match within each window
    5. Cross-step fallback for unmatched
    6. Yield summary
    """
    total = len(photo_names)

    # Phase 1: hash local photos
    local_hashes = await _hash_local_photos(album_dir, photo_names)
    yield UpgradeMatching(phase="hashing_local", done=total, total=total)

    # Phase 2: build time windows and bucket candidates
    windows = build_step_windows(step_timestamps, step_ids)
    google_by_window = _bucket_by_window(google_items, windows)

    # Phase 3: download thumbnails and hash
    all_window_items = [item for items in google_by_window.values() for item in items]
    unique_items = _deduplicate_items(all_window_items)
    candidate_hashes = await _hash_candidates(unique_items, access_token)
    yield UpgradeMatching(
        phase="hashing_candidates", done=len(unique_items), total=len(unique_items)
    )

    # Phase 4: match within each window
    all_matches, matched_locals, matched_candidates = _match_across_windows(
        windows, google_by_window, photo_names, local_hashes, candidate_hashes
    )

    # Phase 5: cross-step fallback
    _cross_step_fallback(
        all_matches,
        matched_locals,
        matched_candidates,
        photo_names,
        local_hashes,
        google_items,
        candidate_hashes,
    )

    # Phase 6: yield summary
    yield UpgradeMatchSummary(
        total_photos=total,
        matched=len(all_matches),
        unmatched=total - len(all_matches),
        matches=all_matches,
    )


def _match_across_windows(
    windows: list[StepWindow],
    google_by_window: dict[int, list[PickedMediaItem]],
    photo_names: list[str],
    local_hashes: dict[str, imagehash.ImageHash],
    candidate_hashes: dict[str, imagehash.ImageHash],
) -> tuple[list[MatchResult], set[str], set[str]]:
    """Run Hungarian matching within each time window."""
    all_matches: list[MatchResult] = []
    matched_locals: set[str] = set()
    matched_candidates: set[str] = set()

    for window in windows:
        window_items = google_by_window[window.step_id]
        unmatched_local = [
            n for n in photo_names if n in local_hashes and n not in matched_locals
        ]
        unmatched_cands = [
            item
            for item in window_items
            if item.id in candidate_hashes and item.id not in matched_candidates
        ]
        if not unmatched_local or not unmatched_cands:
            continue

        results = match_within_window(
            local_names=unmatched_local,
            local_hashes=[local_hashes[n] for n in unmatched_local],
            candidate_ids=[item.id for item in unmatched_cands],
            candidate_hashes=[candidate_hashes[item.id] for item in unmatched_cands],
        )
        for r in results:
            all_matches.append(r)
            matched_locals.add(r.local_name)
            matched_candidates.add(r.google_id)

    return all_matches, matched_locals, matched_candidates


def _cross_step_fallback(  # noqa: PLR0913
    all_matches: list[MatchResult],
    matched_locals: set[str],
    matched_candidates: set[str],
    photo_names: list[str],
    local_hashes: dict[str, imagehash.ImageHash],
    google_items: list[PickedMediaItem],
    candidate_hashes: dict[str, imagehash.ImageHash],
) -> None:
    """Try matching remaining unmatched photos across all windows."""
    remaining_local = [
        n for n in photo_names if n in local_hashes and n not in matched_locals
    ]
    remaining_candidates = [
        item
        for item in google_items
        if item.id in candidate_hashes and item.id not in matched_candidates
    ]

    if (
        remaining_local
        and remaining_candidates
        and len(remaining_local) <= _FALLBACK_MAX_DIMENSION
        and len(remaining_candidates) <= _FALLBACK_MAX_DIMENSION
    ):
        fallback_results = match_within_window(
            local_names=remaining_local,
            local_hashes=[local_hashes[n] for n in remaining_local],
            candidate_ids=[item.id for item in remaining_candidates],
            candidate_hashes=[
                candidate_hashes[item.id] for item in remaining_candidates
            ],
        )
        all_matches.extend(fallback_results)


# ---------------------------------------------------------------------------
# Upgrade execution (post-confirmation)
# ---------------------------------------------------------------------------


def _needs_jpeg_conversion(mime_type: str) -> bool:
    """Check if a MIME type needs conversion to JPEG."""
    return mime_type.lower() not in ("image/jpeg", "image/jpg")


def _convert_to_jpeg_sync(data: bytes) -> bytes:
    """Convert image bytes to JPEG format (synchronous)."""
    with Image.open(BytesIO(data)) as img:
        rgb = img.convert("RGB")
        buf = BytesIO()
        rgb.save(buf, "JPEG", quality=95)
        return buf.getvalue()


def _validate_image(path: Path) -> tuple[int, int]:
    """Open an image and return its (width, height)."""
    with Image.open(path) as img:
        return img.size


async def _download_and_replace(
    match: MatchResult,
    item: PickedMediaItem,
    album_dir: Path,
    tmp_dir: Path,
    access_token: str,
) -> bool:
    """Download one original, validate, and replace the compressed file.

    Returns True on success, False on failure.
    """
    async with _REPLACE_DOWNLOAD_SEM:
        data = await download_media_bytes(item.media_file.base_url, access_token)

    if not data:
        return False

    if _needs_jpeg_conversion(item.media_file.mime_type):
        data = await asyncio.to_thread(_convert_to_jpeg_sync, data)

    tmp_path = tmp_dir / match.local_name
    await asyncio.to_thread(tmp_path.write_bytes, data)

    width, height = await asyncio.to_thread(_validate_image, tmp_path)

    target = album_dir / match.local_name
    if target.exists():
        existing = Media.load(target)
        if width * height <= existing.width * existing.height:
            logger.info(
                "Skipping %s: original (%dx%d) not larger than existing (%dx%d)",
                match.local_name,
                width,
                height,
                existing.width,
                existing.height,
            )
            tmp_path.unlink(missing_ok=True)
            return False

    tmp_path.rename(target)
    delete_thumbnails(target)
    return True


async def execute_upgrade(
    album_dir: Path,
    matches: list[MatchResult],
    google_items_by_id: dict[str, PickedMediaItem],
    access_token: str,
    already_upgraded: dict[str, str],
) -> AsyncIterator[UpgradeEvent]:
    """Download originals and replace compressed files on disk.

    Yields progress events for SSE streaming.
    """
    to_upgrade = [m for m in matches if m.local_name not in already_upgraded]
    total = len(to_upgrade)

    if total == 0:
        yield UpgradeDone(replaced=0, failed=0)
        return

    tmp_dir = album_dir / ".upgrade-tmp"
    tmp_dir.mkdir(exist_ok=True)

    replaced = 0
    failed = 0

    for i, match in enumerate(to_upgrade):
        item = google_items_by_id.get(match.google_id)
        if not item:
            failed += 1
            yield UpgradeDownloading(done=i + 1, total=total)
            continue

        try:
            ok = await _download_and_replace(
                match, item, album_dir, tmp_dir, access_token
            )
        except OSError, SyntaxError:
            logger.exception("Failed to upgrade %s", match.local_name)
            ok = False

        if ok:
            replaced += 1
        else:
            failed += 1
        yield UpgradeDownloading(done=i + 1, total=total)

    with contextlib.suppress(OSError):
        tmp_dir.rmdir()

    yield UpgradeDone(replaced=replaced, failed=failed)
