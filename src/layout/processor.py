"""Photo processing and layout computation for steps."""

from pathlib import Path

from PIL import Image, ImageOps

from src.core.logger import get_logger
from src.core.settings import settings
from src.data.layout import Photo, StepLayout
from src.data.trip import Step

from .scorer import gen_page_layouts

logger = get_logger(__name__)


def build_step_layout(
    step: Step,
    trip_dir: Path,
) -> StepLayout:
    folder = trip_dir / step.folder_name / "photos"
    photos_in_folder = list(map(_load_photo, folder.iterdir()))

    # Determine cover photo
    cover = _select_cover(photos_in_folder)

    # But if it will not appear, leave it tu be put in the pages
    if len(step.description) <= settings.description_two_columns_threshold:
        photos_in_folder.remove(cover)

    return StepLayout(
        id=step.id,
        name=step.name,
        cover=cover.path,
        pages=gen_page_layouts(photos_in_folder),
        hidden_photos=[],
    )


def _load_photo(path: Path) -> Photo:
    with Image.open(path) as img:
        width, height = ImageOps.exif_transpose(img).size

    return Photo(
        path=path.absolute(),
        width=width,
        height=height,
    )


def _select_cover(photos: list[Photo]) -> Photo:
    portraits = [photo for photo in photos if photo.aspect_ratio < 1]

    if portraits:
        return portraits[0]

    return photos[0]
