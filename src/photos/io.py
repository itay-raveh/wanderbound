"""Photo loading and metadata extraction."""

from functools import lru_cache
from pathlib import Path

from PIL import Image

from src.core.logger import get_logger
from src.data.models import Photo

logger = get_logger(__name__)


@lru_cache(maxsize=512)
def _load_photo_metadata(img_path: Path) -> tuple[int, int, float] | None:
    try:
        with Image.open(img_path) as img:
            width, height = img.size
            aspect_ratio = width / height if height > 0 else 0
            return (width, height, aspect_ratio)
    except (OSError, ValueError, AttributeError, TypeError) as e:
        logger.debug("Error loading image metadata for %s: %s", img_path, e)
        return None


def _load_single_photo(img_path: Path, index: int) -> Photo | None:
    metadata = _load_photo_metadata(img_path)
    if metadata is None:
        return None

    width, height, aspect_ratio = metadata
    return Photo(
        id=img_path.name,
        index=index,
        path=img_path,
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
    )


def load_step_photos(photo_dir: Path) -> list[Photo]:
    if not photo_dir.exists():
        logger.warning("Photo directory does not exist: %s", photo_dir)
        return []

    image_extensions = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}
    image_files = sorted(
        [f for f in photo_dir.iterdir() if f.suffix in image_extensions and f.is_file()]
    )

    photos = []
    for index, img_path in enumerate(image_files, start=1):
        photo = _load_single_photo(img_path, index)
        if photo:
            photos.append(photo)

    return photos
