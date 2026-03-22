import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated, Self

from PIL import Image, ImageOps
from PIL.ExifTags import Base as ExifBase
from PIL.Image import Resampling
from pydantic import BaseModel, StringConstraints

from app.core.resources import detect_memory_mb

logger = logging.getLogger(__name__)

MEDIA_EXTENSIONS = frozenset({".jpg", ".mp4"})
# Must match frontend utils/media.ts THUMB_WIDTHS - frontend builds srcset from these.
THUMB_WIDTHS = (200, 800)
THUMB_QUALITY = 80

# Limit concurrent heavy media work (ffmpeg frame extraction, Pillow thumbnails).
_MEDIA_BASELINE_MB = 400  # Python process + other services sharing the container
_PER_MEDIA_OP_MB = 80  # Pillow load + resize + save
_media_budget = max(256, detect_memory_mb() - _MEDIA_BASELINE_MB)
media_sem = asyncio.Semaphore(max(4, min(40, _media_budget // _PER_MEDIA_OP_MB)))


def _generate_thumbnail_sync(source: Path, width: int) -> Path | None:
    with Image.open(source) as raw:
        img = ImageOps.exif_transpose(raw) or raw
        orig_w, orig_h = img.size
        if width >= orig_w:
            return None
        out_dir = source.parent / ".thumbs" / str(width)
        out_dir.mkdir(parents=True, exist_ok=True)
        ratio = width / orig_w
        thumb = img.resize((width, round(orig_h * ratio)), Resampling.LANCZOS)
        out = out_dir / f"{source.stem}.webp"
        thumb.save(out, "WEBP", quality=THUMB_QUALITY)
        return out


async def generate_thumbnail(source: Path, width: int) -> Path | None:
    async with media_sem:
        return await asyncio.to_thread(_generate_thumbnail_sync, source, width)


def delete_thumbnails(path: Path) -> None:
    thumbs_base = path.parent / ".thumbs"
    for w in THUMB_WIDTHS:
        thumb = thumbs_base / str(w) / f"{path.stem}.webp"
        thumb.unlink(missing_ok=True)


# {uuid4}_{uuid4}.(jpg|mp4)
_UUID4 = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

MediaName = Annotated[
    str, StringConstraints(pattern=rf"^{_UUID4}_{_UUID4}\.(jpg|mp4)$")
]


def normalize_name(raw: str) -> str:
    """Fix the .jpg.jpg double-extension from the Polarsteps ZIP format."""
    return raw.replace(".jpg.jpg", ".jpg")


def is_video(name: str) -> bool:
    return name.endswith(".mp4")


async def _video_dimensions(path: Path) -> tuple[int, int]:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
        "-of",
        "json",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {stderr.decode()}")
    streams = json.loads(stdout).get("streams", [])
    if not streams:
        raise RuntimeError(f"No video stream found in {path}")
    stream = streams[0]
    w, h = stream["width"], stream["height"]
    # Legacy: rotate tag in stream metadata
    rotation = abs(int(stream.get("tags", {}).get("rotate", "0")))
    # Modern: display matrix in side_data_list (newer iOS/Android)
    if rotation == 0:
        for sd in stream.get("side_data_list", []):
            if "rotation" in sd:
                rotation = abs(int(sd["rotation"]))
                break
    if rotation in (90, 270):
        w, h = h, w
    logger.debug("ffprobe %s: %dx%d (rotation=%d)", path.name, w, h, rotation)
    return w, h


class Media(BaseModel):
    name: str
    width: int
    height: int

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height

    @property
    def is_portrait(self) -> bool:
        return self.aspect_ratio <= 4 / 5

    @property
    def orientation(self) -> str:
        return "p" if self.is_portrait else "l"

    @classmethod
    def load(cls, path: Path) -> Self:
        with Image.open(path) as img:
            width, height = img.size
            if img.getexif().get(ExifBase.Orientation) in (5, 6, 7, 8):
                width, height = height, width
        return cls(
            name=normalize_name(path.name),
            width=width,
            height=height,
        )

    @classmethod
    async def probe(cls, path: Path) -> Self:
        w, h = await _video_dimensions(path)
        return cls(
            name=normalize_name(path.name),
            width=w,
            height=h,
        )


async def extract_frame(video: Path, timestamp: float = 1) -> Path:
    frame_path = video.with_suffix(".jpg")
    command = [
        "ffmpeg",
        "-y",
        "-threads",
        "1",
        "-loglevel",
        "error",
        "-ss",
        str(timestamp),
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(frame_path),
    ]

    async with media_sem:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

    if process.returncode != 0 or not frame_path.exists():
        raise RuntimeError(f"Failed to extract: {stderr.decode()}")

    return frame_path
