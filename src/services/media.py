import asyncio
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

from src.core.logger import get_logger
from src.models.layout import Photo, Video

logger = get_logger(__name__)


async def load_photo(path: Path) -> Photo:
    """Load photo metadata asynchronously (CPU bound, so threaded)."""
    return await asyncio.to_thread(_load_photo, path)


def _load_photo(path: Path) -> Photo:
    path = path.absolute()

    with Image.open(path) as img:
        width, height = ImageOps.exif_transpose(img).size

    return Photo(
        path=path,
        width=width,
        height=height,
    )


_DEFAULT_FRAME_TS = 1


async def load_video(path: Path, output_dir: Path) -> Video:
    path = path.absolute()

    frame = frame_path(path, _DEFAULT_FRAME_TS, output_dir)
    await extract_frame(path, _DEFAULT_FRAME_TS, frame)

    frame = await load_photo(frame)

    return Video(
        path=frame.path,
        width=frame.width,
        height=frame.height,
        src=path,
        timestamp=_DEFAULT_FRAME_TS,
    )


def frame_path(video_path: Path, timestamp: float, output_dir: Path) -> Path:
    ts_str = f"{timestamp:.3f}".replace(".", "_")
    return (output_dir / "frames" / f"{video_path.stem}__{ts_str}.jpg").absolute()


async def extract_frame(video: Path, timestamp: float, frame: Path) -> None:
    """Extract a single frame from the video at the given timestamp using ffmpeg asynchronously."""
    if frame.exists():
        return

    frame.parent.mkdir(parents=True, exist_ok=True)

    args = [
        "-ss",
        str(timestamp),
        "-i",
        str(video.absolute()),
        "-frames:v",
        "1",
        "-q:v",
        "1",  # Highest quality JPG (1-31 range)
        str(frame.absolute()),
    ]

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        *args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.error("ffmpeg failed: %s", stderr.decode())
