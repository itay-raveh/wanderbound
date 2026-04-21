"""Photo and video processing for media upgrade.

Handles normalization of downloaded originals: EXIF transpose, resize,
JPEG conversion for photos; H.264 re-encode with HDR tone-mapping for videos.
"""

import asyncio
import logging
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
import av
import imagehash
import pillow_heif  # noqa: F401 - registers HEIC plugin for Pillow
from PIL import Image, ImageOps
from PIL.Image import Resampling

from app.logic.layout.media import (
    HDR_COLOR_TRC,
    Media,
    delete_thumbnails,
    extract_frame,
)

logger = logging.getLogger(__name__)

_MAX_LONG_EDGE = 3000
_JPEG_QUALITY = 85


@asynccontextmanager
async def tmp_file(path: Path) -> AsyncIterator[Path]:
    """Yield *path*; unlink it (if present) on exit. Safe after shutil.move."""
    try:
        yield path
    finally:
        await anyio.Path(path).unlink(missing_ok=True)


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
    # stream.color_trc is populated from codec params; no decode needed.
    # https://pyav.basswood-io.com/docs/stable/api/stream.html
    with av.open(str(path)) as container:
        return container.streams.video[0].color_trc in HDR_COLOR_TRC


async def process_video(input_path: Path, output: Path) -> None:
    """Re-encode video: H.264, capped resolution, stripped metadata, HDR tone-mapped.

    Reads from ``input_path``, writes to ``output``. Does not modify
    ``input_path``; the caller owns its lifecycle.
    """
    # Full transcoding pipeline (zscale/tonemap/scale, x264 encoder, AAC, faststart)
    # stays on ffmpeg CLI - PyAV would need a hand-built filter graph + encoder loop.
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

    # -fs truncates mid-stream, producing a corrupt container. Treat as failure.
    size = await asyncio.to_thread(lambda: output.stat().st_size)
    if size >= _MAX_OUTPUT_BYTES:
        msg = f"ffmpeg output hit {_MAX_OUTPUT_BYTES}-byte cap"
        raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# Video frame hashing (perceptual hash of sampled frames, for matching)
# ---------------------------------------------------------------------------

_VIDEO_SAMPLE_POINTS = (0.10, 0.30, 0.50, 0.70)


def extract_video_frame_hashes(path: Path) -> list[imagehash.ImageHash]:
    """Extract frames at 10/30/50/70% of duration and compute pHash for each."""
    # Single container open; seek+decode per sample point.
    # https://pyav.basswood-io.com/docs/stable/api/container.html#av.container.InputContainer.seek
    hashes: list[imagehash.ImageHash] = []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        duration = container.duration / av.time_base if container.duration else 2.0
        for pct in _VIDEO_SAMPLE_POINTS:
            ts = duration * pct
            container.seek(int(ts * av.time_base))
            for frame in container.decode(stream):
                if frame.time is not None and frame.time >= ts:
                    hashes.append(imagehash.phash(frame.to_image()))
                    break
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
    async with tmp_file(tmp_path) as tmp:
        await process_video(raw_path, tmp)
        new_media = await Media.probe(tmp)

        try:
            existing = await Media.probe(target)
        except RuntimeError, OSError:
            logger.debug("Could not probe existing video %s", name, exc_info=True)
            existing = None
        if existing and _skip_smaller(
            name, new_media.width, new_media.height, existing
        ):
            return False

        await asyncio.to_thread(shutil.move, tmp, target)

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
    async with tmp_file(tmp_path) as tmp:
        width, height = await asyncio.to_thread(process_photo_sync, raw_path, tmp)

        try:
            existing = await asyncio.to_thread(Media.load, target)
        except OSError, SyntaxError:
            logger.debug("Could not load existing photo %s", name, exc_info=True)
            existing = None
        if existing and _skip_smaller(name, width, height, existing):
            return False

        await asyncio.to_thread(shutil.move, tmp, target)

    await asyncio.to_thread(delete_thumbnails, target)
    return True
