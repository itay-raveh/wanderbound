"""Select appropriate images for steps based on aspect ratio."""

from enum import Enum
from pathlib import Path

from PIL import Image

from .logger import get_logger

logger = get_logger(__name__)


class PhotoRatio(Enum):
    """Photo aspect ratio categories."""

    PORTRAIT = [(9, 16), (3, 4)]
    LANDSCAPE = [(16, 9), (4, 3)]
    UNKNOWN = None  # Sentinel value


def get_photo_ratio(width: int, height: int) -> PhotoRatio:
    """Get photo ratio category."""
    aspect_ratio = width / height if height > 0 else 0

    for photo_ratio in PhotoRatio:
        if photo_ratio == PhotoRatio.UNKNOWN:
            continue
        ratio_list = (
            list(photo_ratio.value)
            if isinstance(photo_ratio.value, tuple)
            else photo_ratio.value
        )
        for ratio_tuple in ratio_list:
            ratio_width, ratio_height = ratio_tuple
            target_ratio = ratio_width / ratio_height
            if abs(aspect_ratio - target_ratio) < 0.1:
                return photo_ratio

    return PhotoRatio.UNKNOWN


def select_step_image(photo_dir: Path) -> Path | None:
    """Select the best image for a step based on aspect ratio."""
    if not photo_dir.exists():
        return None

    image_files = (
        sorted(photo_dir.glob("*.jpg"))
        + sorted(photo_dir.glob("*.jpeg"))
        + sorted(photo_dir.glob("*.png"))
    )

    if not image_files:
        return None

    for img_path in image_files:
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                ratio = get_photo_ratio(width, height)

                if ratio == PhotoRatio.LANDSCAPE:
                    aspect = width / height
                    if abs(aspect - (4 / 3)) < 0.1:
                        return img_path
        except Exception as e:
            logger.debug(f"Error processing image {img_path}: {e}")
            continue

    for img_path in image_files:
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                ratio = get_photo_ratio(width, height)

                if ratio == PhotoRatio.LANDSCAPE:
                    aspect = width / height
                    if abs(aspect - (16 / 9)) < 0.1:
                        return img_path
        except Exception as e:
            logger.debug(f"Error processing image {img_path}: {e}")
            continue

    for img_path in image_files:
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                ratio = get_photo_ratio(width, height)

                if ratio == PhotoRatio.PORTRAIT:
                    return img_path
        except Exception as e:
            logger.debug(f"Error processing image {img_path}: {e}")
            continue

    for img_path in image_files:
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                if width > height:
                    return img_path
        except Exception as e:
            logger.debug(f"Error processing image {img_path}: {e}")
            continue

    return image_files[0] if image_files else None
