import subprocess
from pathlib import Path

from src.core.logger import get_logger

logger = get_logger(__name__)


def get_duration(video_path: Path) -> float:
    """Get the duration of a video file in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path.absolute()),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)  # noqa: S603
        return float(result.stdout.strip())
    except subprocess.CalledProcessError:
        logger.exception("Failed to get duration for %s", video_path)
        return 0.0


def calculate_frame_path(video_path: Path, timestamp: float, output_dir: Path) -> Path:
    ts_str = f"{timestamp:.3f}".replace(".", "_")
    return (output_dir / "frames" / f"{video_path.stem}__{ts_str}.jpg").absolute()


def extract_frame(video_path: Path, timestamp: float, output_path: Path) -> None:
    """Extract a single frame from the video at the given timestamp using ffmpeg."""
    if output_path.exists():
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-ss",
        str(timestamp),
        "-i",
        str(video_path.absolute()),
        "-frames:v",
        "1",
        "-q:v",
        "1",  # Highest quality JPG (1-31 range)
        str(output_path.absolute()),
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)  # noqa: S603
    except subprocess.CalledProcessError as e:
        logger.exception("ffmpeg failed: %s", e.stderr)  # pyright: ignore[reportAny]
        raise
