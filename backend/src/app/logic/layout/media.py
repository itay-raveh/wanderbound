import asyncio
from io import BytesIO
from typing import TYPE_CHECKING, Self

from PIL import Image, ImageOps
from pydantic import BaseModel

if TYPE_CHECKING:
    from pathlib import Path


class Photo(BaseModel):
    path: Path
    width: int
    height: int

    def __hash__(self) -> int:
        return hash(self.path)

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height

    @property
    def is_portrait(self) -> float:
        return self.aspect_ratio <= 4 / 5

    @classmethod
    async def load(cls, root: Path, path: Path) -> Self:
        with Image.open(BytesIO(path.read_bytes())) as img:
            width, height = ImageOps.exif_transpose(img).size

        del img

        return cls(
            path=path.relative_to(root),
            width=width,
            height=height,
        )


class Video(Photo):
    src: Path
    timestamp: float

    @classmethod
    async def load(cls, root: Path, path: Path, timestamp: float = 1) -> Self:
        frame_path = await extract_frame(path, timestamp)
        frame = await Photo.load(root, frame_path)

        return cls(
            path=frame.path,
            width=frame.width,
            height=frame.height,
            src=path.relative_to(root),
            timestamp=timestamp,
        )


Media = Video | Photo


async def _is_hdr(video: Path) -> bool:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=color_transfer",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video),
    ]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, _ = await process.communicate()

    if process.returncode != 0:
        return False

    curve = stdout.decode("utf-8").strip().lower()

    return curve in (
        # Samsung HDR10+, standard HDR10, Pro Cameras
        "smpte2084",
        # Apple iPhone Dolby Vision / HDR
        "arib-std-b67",
    )


_HDR_TO_SDR_FILTER = (
    # Prepares the light levels for tone mapping
    "zscale=t=linear:npl=100,"
    # Converts to a 32-bit floating point format for precise math
    "format=gbrpf32le,"
    # Applies the Mobius tone mapping algorithm
    "tonemap=mobius,"
    # Converts the color space to standard BT.709 (SDR)
    "zscale=p=bt709:t=bt709:m=bt709,"
    #  Finalizes the format for a standard PNG output
    "format=rgb24"
)


async def extract_frame(video: Path, timestamp: float) -> Path:
    frame_path = video.with_suffix(".png")

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(timestamp),
        "-i",
        str(video),
        "-frames:v",
        "1",
    ]

    # Add HDR filter if needed
    if await _is_hdr(video):
        command.extend(["-vf", _HDR_TO_SDR_FILTER])

    # Optimize PNG compression
    command.extend(["-pred", "mixed", str(frame_path)])

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    _, stderr = await process.communicate()

    if process.returncode != 0 or not frame_path.exists():
        raise RuntimeError(f"Failed to extract: {stderr.decode()}")

    return frame_path
