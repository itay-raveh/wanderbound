"""Photo loading and metadata extraction."""

from pathlib import Path

from PIL import Image, ImageOps

from src.core.logger import get_logger
from src.data.models import Photo

logger = get_logger(__name__)


def load_single_photo(img_path: Path) -> Photo:
    with Image.open(img_path) as img:
        img_rotated = ImageOps.exif_transpose(img)
        width, height = img_rotated.size

    return Photo(
        id=img_path.name,
        path=img_path,
        width=width,
        height=height,
    )


def load_step_photos(photo_dir: Path) -> list[Photo]:
    if not photo_dir.exists():
        logger.warning("Photo directory does not exist: %s", photo_dir)
        return []

    return list(map(load_single_photo, photo_dir.iterdir()))
