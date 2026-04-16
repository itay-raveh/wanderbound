"""Photo matching and upgrade logic.

Matches compressed Polarsteps photos to Google Photos originals using
perceptual hashing (pHash) and the Hungarian algorithm for optimal
bipartite assignment.
"""

import asyncio
import contextlib
import logging
import subprocess
from collections.abc import AsyncIterator
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Literal

import imagehash
import numpy as np
import pillow_heif  # noqa: F401 - registers HEIC plugin for Pillow
from PIL import Image, ImageOps
from PIL.Image import Resampling
from pydantic import BaseModel
from scipy.optimize import linear_sum_assignment

from app.logic.layout.media import Media, delete_thumbnails, is_video
from app.services.google_photos import (
    AccessToken,
    GoogleMediaId,
    PhotoFilename,
    PickedMediaItem,
    download_media_bytes,
)

logger = logging.getLogger(__name__)

# Hamming distance threshold for accepting a match.
MATCH_THRESHOLD = 12

# Skip cross-step fallback if the matrix exceeds this size.
_FALLBACK_MAX_DIMENSION = 100

# Bounded concurrency for Google Photos downloads (matching + replacement).
_DOWNLOAD_SEM = asyncio.Semaphore(5)

type LocalHash = imagehash.ImageHash | list[imagehash.ImageHash]


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
    local_name: PhotoFilename
    google_id: GoogleMediaId
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
# Video frame hashing
# ---------------------------------------------------------------------------

_VIDEO_SAMPLE_POINTS = (0.10, 0.30, 0.50, 0.70)


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
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 2.0


def _extract_video_frames(path: Path) -> list[imagehash.ImageHash]:
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
        )
        with Image.open(BytesIO(result.stdout)) as img:
            hashes.append(compute_phash(img))
    return hashes


# ---------------------------------------------------------------------------
# Cost matrix and Hungarian matching
# ---------------------------------------------------------------------------


_CROSS_TYPE_COST = 999  # above any possible match threshold


def _hash_distance(local: LocalHash, candidate: imagehash.ImageHash) -> int:
    """Compute distance between a local hash (single or multi-frame) and a candidate."""
    if isinstance(local, imagehash.ImageHash):
        return int(local - candidate)
    return min(int(frame - candidate) for frame in local)


def build_cost_matrix(
    local_hashes: list[LocalHash],
    candidate_hashes: list[imagehash.ImageHash],
    local_is_video: list[bool],
    candidate_is_video: list[bool],
) -> list[list[int]]:
    """Build a distance matrix. Cross-type pairs get infinite cost."""
    matrix: list[list[int]] = []
    for i, lh in enumerate(local_hashes):
        row: list[int] = []
        for j, ch in enumerate(candidate_hashes):
            if local_is_video[i] != candidate_is_video[j]:
                row.append(_CROSS_TYPE_COST)
            else:
                row.append(_hash_distance(lh, ch))
        matrix.append(row)
    return matrix


def match_within_window(  # noqa: PLR0913
    local_names: list[PhotoFilename],
    local_hashes: list[LocalHash],
    candidate_ids: list[GoogleMediaId],
    candidate_hashes: list[imagehash.ImageHash],
    local_is_video: list[bool],
    candidate_is_video: list[bool],
    threshold: int = MATCH_THRESHOLD,
) -> list[MatchResult]:
    """Run Hungarian algorithm on a cost matrix, reject pairs above threshold."""
    if not local_names or not candidate_ids:
        return []

    cost = np.array(
        build_cost_matrix(
            local_hashes, candidate_hashes, local_is_video, candidate_is_video
        )
    )
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
        return datetime.fromisoformat(create_time).timestamp()
    except ValueError:
        return None


def _bucket_by_window(
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


def _deduplicate_items(
    items: list[PickedMediaItem],
) -> list[PickedMediaItem]:
    """Remove duplicate items by ID, preserving order."""
    return list({item.id: item for item in items}.values())


async def _hash_local_media(
    album_dir: Path,
    media_names: list[PhotoFilename],
) -> dict[PhotoFilename, LocalHash]:
    """Compute perceptual hashes for local media files (concurrent).

    Photos: single pHash. Videos: list of 4 pHashes from sampled frames.
    """

    async def _hash_one(name: str) -> tuple[str, LocalHash | None]:
        path = album_dir / name
        if not path.exists():
            return name, None
        try:
            if is_video(name):
                return name, await asyncio.to_thread(_extract_video_frames, path)
            return name, await asyncio.to_thread(compute_phash_from_path, path)
        except OSError, SyntaxError, subprocess.CalledProcessError:
            logger.warning("Failed to hash %s", name, exc_info=True)
            return name, None

    results = await asyncio.gather(*(_hash_one(n) for n in media_names))
    return {name: h for name, h in results if h is not None}


async def _hash_candidates(
    items: list[PickedMediaItem],
    access_token: AccessToken,
) -> dict[GoogleMediaId, imagehash.ImageHash]:
    """Download thumbnails and compute perceptual hashes (concurrent)."""

    async def _hash_one(
        item: PickedMediaItem,
    ) -> tuple[str, imagehash.ImageHash | None]:
        try:
            thumb_param = "=w400-no" if item.type == "VIDEO" else "=w400"
            async with _DOWNLOAD_SEM:
                thumb_bytes = await download_media_bytes(
                    item.media_file.base_url, access_token, param=thumb_param
                )
            return item.id, await asyncio.to_thread(
                compute_phash_from_bytes, thumb_bytes
            )
        except OSError, SyntaxError:
            logger.warning(
                "Failed to download/hash thumbnail for %s",
                item.id,
                exc_info=True,
            )
            return item.id, None

    results = await asyncio.gather(*(_hash_one(item) for item in items))
    return {item_id: h for item_id, h in results if h is not None}


# ---------------------------------------------------------------------------
# Full matching pipeline
# ---------------------------------------------------------------------------


async def run_matching(  # noqa: PLR0913
    album_dir: Path,
    media_names: list[PhotoFilename],
    step_timestamps: list[float],
    step_ids: list[int],
    google_items: list[PickedMediaItem],
    access_token: AccessToken,
) -> AsyncIterator[UpgradeEvent]:
    """Run the full matching pipeline, yielding SSE events for progress.

    1. Hash local media (photos + videos)
    2. Bucket Google items into step windows
    3. Download thumbnails and hash them
    4. Hungarian match within each window
    5. Cross-step fallback for unmatched
    6. Yield summary
    """
    total = len(media_names)

    local_hashes = await _hash_local_media(album_dir, media_names)
    yield UpgradeMatching(phase="hashing_local", done=total, total=total)

    windows = build_step_windows(step_timestamps, step_ids)
    google_by_window = _bucket_by_window(google_items, windows)

    all_window_items = [item for items in google_by_window.values() for item in items]
    unique_items = _deduplicate_items(all_window_items)
    candidate_hashes = await _hash_candidates(unique_items, access_token)
    yield UpgradeMatching(
        phase="hashing_candidates", done=len(unique_items), total=len(unique_items)
    )

    all_matches, matched_locals, matched_candidates = _match_across_windows(
        windows, google_by_window, media_names, local_hashes, candidate_hashes
    )

    _cross_step_fallback(
        all_matches,
        matched_locals,
        matched_candidates,
        media_names,
        local_hashes,
        google_items,
        candidate_hashes,
    )

    yield UpgradeMatchSummary(
        total_photos=total,
        matched=len(all_matches),
        unmatched=total - len(all_matches),
        matches=all_matches,
    )


def _match_across_windows(
    windows: list[StepWindow],
    google_by_window: dict[int, list[PickedMediaItem]],
    media_names: list[PhotoFilename],
    local_hashes: dict[PhotoFilename, LocalHash],
    candidate_hashes: dict[GoogleMediaId, imagehash.ImageHash],
) -> tuple[list[MatchResult], set[PhotoFilename], set[GoogleMediaId]]:
    """Run Hungarian matching within each time window."""
    all_matches: list[MatchResult] = []
    matched_locals: set[PhotoFilename] = set()
    matched_candidates: set[GoogleMediaId] = set()

    for window in windows:
        window_items = google_by_window[window.step_id]
        unmatched_local = [
            n for n in media_names if n in local_hashes and n not in matched_locals
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
            local_is_video=[is_video(n) for n in unmatched_local],
            candidate_is_video=[item.type == "VIDEO" for item in unmatched_cands],
        )
        for r in results:
            all_matches.append(r)
            matched_locals.add(r.local_name)
            matched_candidates.add(r.google_id)

    return all_matches, matched_locals, matched_candidates


def _cross_step_fallback(  # noqa: PLR0913
    all_matches: list[MatchResult],
    matched_locals: set[PhotoFilename],
    matched_candidates: set[GoogleMediaId],
    media_names: list[PhotoFilename],
    local_hashes: dict[PhotoFilename, LocalHash],
    google_items: list[PickedMediaItem],
    candidate_hashes: dict[GoogleMediaId, imagehash.ImageHash],
) -> None:
    """Try matching remaining unmatched media across all windows."""
    remaining_local = [
        n for n in media_names if n in local_hashes and n not in matched_locals
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
            local_is_video=[is_video(n) for n in remaining_local],
            candidate_is_video=[item.type == "VIDEO" for item in remaining_candidates],
        )
        all_matches.extend(fallback_results)


# ---------------------------------------------------------------------------
# Upgrade execution (post-confirmation)
# ---------------------------------------------------------------------------


_MAX_LONG_EDGE = 3000
_JPEG_QUALITY = 85


def _process_photo_sync(data: bytes) -> bytes:
    """Normalize a downloaded original: transpose, resize, strip EXIF, save as JPEG."""
    with Image.open(BytesIO(data)) as raw:
        img = ImageOps.exif_transpose(raw) or raw
        img = img.convert("RGB")

        w, h = img.size
        long_edge = max(w, h)
        if long_edge > _MAX_LONG_EDGE:
            scale = _MAX_LONG_EDGE / long_edge
            img = img.resize(
                (round(w * scale), round(h * scale)),
                Resampling.LANCZOS,
            )

        buf = BytesIO()
        img.save(buf, "JPEG", quality=_JPEG_QUALITY)
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
    access_token: AccessToken,
) -> bool:
    """Download one original, validate, and replace the compressed file.

    Returns True on success, False on failure.
    """
    async with _DOWNLOAD_SEM:
        data = await download_media_bytes(item.media_file.base_url, access_token)

    if not data:
        return False

    data = await asyncio.to_thread(_process_photo_sync, data)

    tmp_path = tmp_dir / match.local_name
    await asyncio.to_thread(tmp_path.write_bytes, data)

    width, height = await asyncio.to_thread(_validate_image, tmp_path)

    target = album_dir / match.local_name
    try:
        existing = Media.load(target)
    except OSError:
        existing = None
    if existing and width * height <= existing.width * existing.height:
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
    google_items_by_id: dict[GoogleMediaId, PickedMediaItem],
    access_token: AccessToken,
    already_upgraded: dict[PhotoFilename, GoogleMediaId],
) -> AsyncIterator[UpgradeEvent]:
    """Download originals and replace compressed files concurrently.

    Yields progress events for SSE streaming as each download completes.
    """
    to_upgrade = [m for m in matches if m.local_name not in already_upgraded]
    total = len(to_upgrade)

    if total == 0:
        yield UpgradeDone(replaced=0, failed=0)
        return

    tmp_dir = album_dir / ".upgrade-tmp"
    tmp_dir.mkdir(exist_ok=True)

    async def _upgrade_one(match: MatchResult) -> bool:
        item = google_items_by_id.get(match.google_id)
        if not item:
            return False
        try:
            return await _download_and_replace(
                match, item, album_dir, tmp_dir, access_token
            )
        except OSError, SyntaxError:
            logger.exception("Failed to upgrade %s", match.local_name)
            return False

    tasks = [asyncio.create_task(_upgrade_one(m)) for m in to_upgrade]
    replaced = 0
    failed = 0

    for i, coro in enumerate(asyncio.as_completed(tasks)):
        ok = await coro
        if ok:
            replaced += 1
        else:
            failed += 1
        yield UpgradeDownloading(done=i + 1, total=total)

    with contextlib.suppress(OSError):
        tmp_dir.rmdir()

    yield UpgradeDone(replaced=replaced, failed=failed)


async def apply_upgrade_results(
    album_dir: Path,
    matches: list[MatchResult],
    media: list[Media],
    upgraded_photos: dict[PhotoFilename, GoogleMediaId],
) -> tuple[list[Media], dict[PhotoFilename, GoogleMediaId]]:
    """Re-probe replaced files and update media list + upgrade map.

    Returns the updated (media, upgraded_photos) for the caller to persist.
    """
    media_by_name = {m.name: m for m in media}
    for match in matches:
        target = album_dir / match.local_name
        try:
            updated = await asyncio.to_thread(Media.load, target)
            if match.local_name in media_by_name:
                media_by_name[match.local_name] = updated
        except OSError, SyntaxError:
            logger.warning("Failed to re-probe %s", match.local_name, exc_info=True)
        upgraded_photos[match.local_name] = match.google_id
    return list(media_by_name.values()), upgraded_photos
