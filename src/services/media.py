"""Photo processing and layout computation for steps."""

from pathlib import Path

from PIL import Image, ImageOps

from src.core.logger import get_logger
from src.models.layout import Photo, Video
from src.services import video

logger = get_logger(__name__)


def load_photo(path: Path) -> Photo:
    path = path.absolute()

    with Image.open(path) as img:
        width, height = ImageOps.exif_transpose(img).size

    return Photo(
        path=path,
        width=width,
        height=height,
    )


def load_video(path: Path, output_dir: Path) -> Video:
    path = path.absolute()

    duration = video.get_duration(path)
    timestamp = duration / 2

    frame_path = video.calculate_frame_path(path, timestamp, output_dir)
    video.extract_frame(path, timestamp, frame_path)

    frame = load_photo(frame_path)

    return Video(
        path=frame.path,
        width=frame.width,
        height=frame.height,
        video_src=path,
        video_timestamp=timestamp,
    )
