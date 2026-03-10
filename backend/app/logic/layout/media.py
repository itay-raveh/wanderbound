import asyncio
from typing import TYPE_CHECKING, Self

from PIL import Image
from PIL.ExifTags import Base as ExifBase
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
    def load(cls, root: Path, path: Path) -> Self:
        with Image.open(path) as img:
            width, height = img.size
            # Orientations 5-8 involve a 90-degree rotation
            if img.getexif().get(ExifBase.Orientation) in (5, 6, 7, 8):
                width, height = height, width

        return cls(
            path=path.relative_to(root),
            width=width,
            height=height,
        )


class Video(Photo):
    src: Path
    timestamp: float

    @classmethod
    async def extract(cls, root: Path, path: Path, timestamp: float = 1) -> Self:
        frame_path = await extract_frame(path, timestamp)
        frame = Photo.load(root, frame_path)

        return cls(
            path=frame.path,
            width=frame.width,
            height=frame.height,
            src=path.relative_to(root),
            timestamp=timestamp,
        )


Media = Video | Photo


async def _hdr_transfer(video: Path) -> str | None:
    """Return the HDR transfer curve name, or None for SDR content."""
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
        return None

    curve = stdout.decode("utf-8").strip().lower()

    if curve in (
        "smpte2084",  # HDR10, HDR10+, Dolby Vision (PQ-based profiles)
        "arib-std-b67",  # HLG — iPhone Dolby Vision Profile 8.4
    ):
        return curve

    return None


# https://ericswpark.com/blog/2022/2022-12-14-ffmpeg-convert-hdr-to-sdr/
# https://ayosec.github.io/ffmpeg-filters-docs/8.0/Filters/Video/zscale.html
# https://ayosec.github.io/ffmpeg-filters-docs/7.1/Filters/Video/tonemap.html
def _hdr_to_sdr_filter(transfer: str) -> str:
    """Build an HDR-to-SDR tone mapping filter chain for the given transfer curve."""
    return (
        # Linearize with explicit input color space parameters
        f"zscale=tin={transfer}:min=bt2020nc:pin=bt2020:rin=tv:t=linear:npl=1000,"
        # 32-bit float for precise tone mapping
        "format=gbrpf32le,"
        # Filmic tone mapping — preserves detail in darks and highlights
        "tonemap=hable:desat=0,"
        # Convert to SDR color space, full range for PNG output
        "zscale=p=bt709:t=bt709:m=bt709:r=full,"
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

    # Add HDR-to-SDR tone mapping if needed
    transfer = await _hdr_transfer(video)
    if transfer:
        command.extend(["-vf", _hdr_to_sdr_filter(transfer)])

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
