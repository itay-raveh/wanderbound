"""Photo and video processing for media upgrade.

Handles normalization of downloaded originals: EXIF transpose, resize,
JPEG conversion for photos; H.264 re-encode with HDR tone-mapping for videos.
"""

import asyncio
import logging
import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import imagehash
import pillow_heif  # noqa: F401 - registers HEIC plugin for Pillow
from PIL import Image, ImageOps
from PIL.Image import Resampling

from app.logic.layout.media import Media, delete_thumbnails, extract_frame

logger = logging.getLogger(__name__)

_MAX_LONG_EDGE = 3000
_JPEG_QUALITY = 85


def process_photo_sync(raw_path: Path, tmp_path: Path) -> tuple[int, int]:
    """Normalize a downloaded original: transpose, resize, strip EXIF, save as JPEG.

    Reads from ``raw_path`` and writes the processed JPEG to ``tmp_path``.
    Returns ``(width, height)``.
    """
    with Image.open(raw_path) as raw:
        img = ImageOps.exif_transpose(raw) or raw
        img = img.convert("RGB")

        long_edge = max(img.size)
        if long_edge > _MAX_LONG_EDGE:
            scale = _MAX_LONG_EDGE / long_edge
            w, h = img.size
            img = img.resize(
                (round(w * scale), round(h * scale)),
                Resampling.LANCZOS,
            )

        img.save(tmp_path, "JPEG", quality=_JPEG_QUALITY)
        return img.size


# ---------------------------------------------------------------------------
# Video processing
# ---------------------------------------------------------------------------

_FFPROBE_TIMEOUT = 30
_VIDEO_CRF = "23"
_VIDEO_PRESET = "medium"
_AUDIO_BITRATE = "128k"
_REENCODE_TIMEOUT = 600  # 10 minutes for video re-encode
_MAX_OUTPUT_BYTES = 500 * 1024 * 1024  # ~10m phone video at CRF 23

_HDR_TONEMAP_FILTER = (
    "zscale=t=linear:npl=100,format=gbrpf32le,"
    "zscale=p=bt709,tonemap=hable:desat=0,"
    "zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
)


def _detect_hdr(path: Path) -> bool:
    """Check if a video has HDR color transfer characteristics."""
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=color_transfer",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=_FFPROBE_TIMEOUT,
    )
    transfer = result.stdout.strip()
    return transfer in ("smpte2084", "arib-std-b67")  # PQ (HDR10) or HLG


async def process_video(input_path: Path, output: Path) -> None:
    """Re-encode video: H.264, capped resolution, stripped metadata, HDR tone-mapped.

    Reads from ``input_path``, writes to ``output``. Does not modify
    ``input_path``; the caller owns its lifecycle.
    """
    is_hdr = await asyncio.to_thread(_detect_hdr, input_path)

    scale_filter = (
        f"scale='min({_MAX_LONG_EDGE},iw)':'min({_MAX_LONG_EDGE},ih)'"
        ":force_original_aspect_ratio=decrease:force_divisible_by=2"
    )

    vf = f"{_HDR_TONEMAP_FILTER},{scale_filter}" if is_hdr else scale_filter

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-crf",
        _VIDEO_CRF,
        "-preset",
        _VIDEO_PRESET,
        "-c:a",
        "aac",
        "-b:a",
        _AUDIO_BITRATE,
        "-map_metadata",
        "-1",
        "-movflags",
        "+faststart",
        "-fs",
        str(_MAX_OUTPUT_BYTES),
        str(output),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_REENCODE_TIMEOUT
        )
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(
            f"ffmpeg re-encode timed out after {_REENCODE_TIMEOUT}s"
        ) from None

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg re-encode failed: {stderr.decode()}")

    # -fs stops writing once the cap is reached, producing a truncated file
    # whose container is typically unreadable. Treat it as an explicit failure.
    size = await asyncio.to_thread(lambda: output.stat().st_size)
    if size >= _MAX_OUTPUT_BYTES:
        msg = f"ffmpeg output hit {_MAX_OUTPUT_BYTES}-byte cap"
        raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# Video frame hashing (perceptual hash of sampled frames, for matching)
# ---------------------------------------------------------------------------

_VIDEO_SAMPLE_POINTS = (0.10, 0.30, 0.50, 0.70)
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
            hashes.append(imagehash.phash(img))
    return hashes


# ---------------------------------------------------------------------------
# Replace helpers
# ---------------------------------------------------------------------------


def _skip_smaller(name: str, new_w: int, new_h: int, existing: Media) -> bool:
    """Log and return True when the new file is not larger than existing."""
    if new_w * new_h <= existing.width * existing.height:
        logger.info(
            "Skipping %s: original (%dx%d) not larger than existing (%dx%d)",
            name,
            new_w,
            new_h,
            existing.width,
            existing.height,
        )
        return True
    return False


async def replace_video(
    name: str, raw_path: Path, tmp_path: Path, target: Path
) -> bool:
    """Process and replace a single video. Returns True on success."""
    try:
        await process_video(raw_path, tmp_path)
        new_media = await Media.probe(tmp_path)

        try:
            existing = await Media.probe(target)
        except RuntimeError, OSError:
            logger.debug("Could not probe existing video %s", name, exc_info=True)
            existing = None
        if existing and _skip_smaller(
            name, new_media.width, new_media.height, existing
        ):
            return False

        await asyncio.to_thread(shutil.move, tmp_path, target)
    finally:
        await asyncio.to_thread(lambda: tmp_path.unlink(missing_ok=True))

    # Video already replaced on disk - thumbnail/poster cleanup is best-effort.
    try:
        await asyncio.to_thread(delete_thumbnails, target)
        poster = target.with_suffix(".jpg")
        if await asyncio.to_thread(poster.exists):
            await asyncio.to_thread(delete_thumbnails, poster)
        await extract_frame(target)
    except OSError:
        logger.warning("Thumbnail cleanup failed for %s", name, exc_info=True)
    return True


async def replace_photo(
    name: str, raw_path: Path, tmp_path: Path, target: Path
) -> bool:
    """Process and replace a single photo. Returns True on success."""
    try:
        width, height = await asyncio.to_thread(process_photo_sync, raw_path, tmp_path)

        try:
            existing = await asyncio.to_thread(Media.load, target)
        except OSError, SyntaxError:
            logger.debug("Could not load existing photo %s", name, exc_info=True)
            existing = None
        if existing and _skip_smaller(name, width, height, existing):
            return False

        await asyncio.to_thread(shutil.move, tmp_path, target)
    finally:
        await asyncio.to_thread(lambda: tmp_path.unlink(missing_ok=True))

    await asyncio.to_thread(delete_thumbnails, target)
    return True
