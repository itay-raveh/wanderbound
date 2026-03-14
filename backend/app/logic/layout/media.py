import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated, Self

from PIL import Image, ImageOps
from PIL.ExifTags import Base as ExifBase
from PIL.Image import Resampling
from pydantic import BaseModel, StringConstraints

logger = logging.getLogger(__name__)

MEDIA_EXTENSIONS = frozenset({".jpg", ".mp4"})
THUMB_WIDTHS = (400, 1200)
THUMB_QUALITY = 80


def _generate_thumbnails_sync(path: Path) -> None:
    thumbs_base = path.parent / ".thumbs"
    with Image.open(path) as raw:
        img = ImageOps.exif_transpose(raw) or raw
        orig_w, orig_h = img.size
        for width in THUMB_WIDTHS:
            if width >= orig_w:
                continue
            out_dir = thumbs_base / str(width)
            out_dir.mkdir(parents=True, exist_ok=True)
            ratio = width / orig_w
            thumb = img.resize((width, round(orig_h * ratio)), Resampling.LANCZOS)
            thumb.save(out_dir / f"{path.stem}.webp", "WEBP", quality=THUMB_QUALITY)


async def generate_thumbnails(path: Path) -> None:
    """Pre-generate WebP thumbnails at multiple widths."""
    await asyncio.to_thread(_generate_thumbnails_sync, path)


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
    """Get video display dimensions via ffprobe, accounting for rotation."""
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


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Photo(BaseModel):
    path: str  # MediaName (just the filename)
    width: int
    height: int

    def __hash__(self) -> int:
        return hash(self.path)

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
            path=normalize_name(path.name),
            width=width,
            height=height,
        )


class Video(Photo):
    src: str  # MediaName (just the filename, .mp4)

    @classmethod
    async def probe(cls, path: Path) -> Self:
        """Get video dimensions via ffprobe — no frame extraction."""
        w, h = await _video_dimensions(path)
        return cls(
            path=normalize_name(path.with_suffix(".jpg").name),
            width=w,
            height=h,
            src=normalize_name(path.name),
        )


Media = Video | Photo


async def extract_frame(video: Path, timestamp: float = 1) -> Path:
    frame_path = video.with_suffix(".jpg")

    command = [
        "ffmpeg",
        "-y",
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

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await process.communicate()

    if process.returncode != 0 or not frame_path.exists():
        raise RuntimeError(f"Failed to extract: {stderr.decode()}")

    return frame_path
