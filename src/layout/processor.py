"""Photo processing and layout computation for steps."""

from pathlib import Path

from PIL import Image, ImageOps

from src.core.logger import get_logger
from src.data.layout import Photo, StepLayout, Video
from src.data.trip import Step
from src.services import video

from .scorer import gen_page_layouts

logger = get_logger(__name__)


def build_step_layout(
    step: Step,
    trip_dir: Path,
    output_dir: Path,
) -> StepLayout:
    assets_in_folder: list[Video | Photo] = []

    # Load Photos
    photo_folder = trip_dir / step.folder_name / "photos"
    if photo_folder.exists():
        assets_in_folder = list(map(load_photo, photo_folder.iterdir()))

    # Try select cover
    cover: Photo | None = None
    if assets_in_folder:
        cover = _select_cover(assets_in_folder)

    # Load Videos
    video_folder = trip_dir / step.folder_name / "videos"
    if video_folder.exists():
        assets_in_folder.extend(
            load_video(video_path, output_dir) for video_path in video_folder.iterdir()
        )

    cover = cover or _select_cover(assets_in_folder)

    # If it appears on the step page, remove it from the photo pages
    if not step.is_long_description:
        assets_in_folder.remove(cover)

    return StepLayout(
        id=step.id,
        name=step.name,
        cover=cover.path,
        pages=gen_page_layouts(assets_in_folder),
        hidden_photos=[],
    )


def _select_cover(photos: list[Photo]) -> Photo:
    portraits = [photo for photo in photos if photo.is_portrait]

    if portraits:
        return portraits[0]

    return photos[0]


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
