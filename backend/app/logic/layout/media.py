import asyncio
import json
from pathlib import Path
from typing import Annotated, Literal, Self

from PIL import Image
from PIL.ExifTags import Base as ExifBase
from pydantic import BaseModel, StringConstraints

MEDIA_EXTENSIONS = frozenset({".jpg", ".mp4"})
THUMB_WIDTHS = (400, 1200)
type ThumbWidth = Literal[400, 1200]
THUMB_QUALITY = 80


def _get_image_width(path: Path) -> int:
    """Get display width of an image, accounting for EXIF rotation."""
    with Image.open(path) as img:
        w, h = img.size
        if img.getexif().get(ExifBase.Orientation) in (5, 6, 7, 8):
            w, h = h, w
        return w


async def generate_thumbnails(path: Path) -> None:
    """Pre-generate WebP thumbnails via ffmpeg (single process, multiple outputs).

    ffmpeg handles EXIF auto-rotation, JPEG decoding, scaling, and WebP
    encoding much faster than Pillow — especially for large images.
    """
    orig_w = await asyncio.to_thread(_get_image_width, path)
    widths = [w for w in THUMB_WIDTHS if w < orig_w]
    if not widths:
        return

    thumbs_base = path.parent / ".thumbs"
    stem = path.stem

    # Build ffmpeg command with split filter for all widths in one pass.
    n = len(widths)
    split_labels = "".join(f"[s{i}]" for i in range(n))
    filter_parts = [f"[0:v]split={n}{split_labels}"]
    cmd: list[str] = ["ffmpeg", "-y", "-i", str(path)]
    maps: list[str] = []

    for i, w in enumerate(widths):
        out_dir = thumbs_base / str(w)
        await asyncio.to_thread(out_dir.mkdir, parents=True, exist_ok=True)
        out_path = out_dir / f"{stem}.webp"
        filter_parts.append(f"[s{i}]scale={w}:-1[out{i}]")
        maps.extend(
            [
                "-map",
                f"[out{i}]",
                "-c:v",
                "libwebp",
                "-quality",
                str(THUMB_QUALITY),
                str(out_path),
            ]
        )

    cmd.extend(["-filter_complex", "; ".join(filter_parts)])
    cmd.extend(maps)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Thumbnail generation failed: {stderr.decode()}")


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
        "stream=width,height:stream_tags=rotate",
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
    rotation = abs(int(stream.get("tags", {}).get("rotate", "0")))
    if rotation in (90, 270):
        w, h = h, w
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
