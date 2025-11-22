"""Select appropriate images for steps based on aspect ratio."""

from pathlib import Path
from typing import Optional
from enum import Enum
from PIL import Image


class PhotoRatio(Enum):
    """Photo aspect ratio categories."""
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"
    SQUARE = "square"


def get_image_aspect_ratio(image_path: Path) -> Optional[float]:
    """Get aspect ratio (width/height) of an image."""
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            return width / height if height > 0 else None
    except Exception:
        return None


def get_photo_ratio(image_path: Path) -> Optional[PhotoRatio]:
    """Get photo ratio category."""
    ratio = get_image_aspect_ratio(image_path)
    if ratio is None:
        return None
    
    if ratio < 0.9:
        return PhotoRatio.PORTRAIT
    elif ratio > 1.1:
        return PhotoRatio.LANDSCAPE
    else:
        return PhotoRatio.SQUARE


def is_portrait(image_path: Path) -> bool:
    """Check if image is portrait (height > width)."""
    return get_photo_ratio(image_path) == PhotoRatio.PORTRAIT


def select_step_image(photo_dir: Path) -> Optional[Path]:
    """
    Select the best image for a step.
    Priority: 5:4 horizontal (1.25), then 4:3 (1.33), then any landscape, then portrait.
    """
    if not photo_dir.exists():
        return None

    image_files = (
        sorted(photo_dir.glob("*.jpg"))
        + sorted(photo_dir.glob("*.jpeg"))
        + sorted(photo_dir.glob("*.png"))
    )

    if not image_files:
        return None

    # Target aspect ratio for 5:4 horizontal (1.25) - preferred
    target_ratio_5_4 = 1.25
    target_ratio_4_3 = 1.33
    tolerance = 0.1

    # First priority: 5:4 horizontal (exact match preferred)
    for img_path in image_files:
        ratio = get_image_aspect_ratio(img_path)
        if ratio and abs(ratio - target_ratio_5_4) <= tolerance:
            return img_path

    # Second priority: 4:3 horizontal
    for img_path in image_files:
        ratio = get_image_aspect_ratio(img_path)
        if ratio and abs(ratio - target_ratio_4_3) <= tolerance:
            return img_path

    # Third priority: Any landscape image
    for img_path in image_files:
        if get_photo_ratio(img_path) == PhotoRatio.LANDSCAPE:
            return img_path

    # Fourth priority: Portrait image
    for img_path in image_files:
        if get_photo_ratio(img_path) == PhotoRatio.PORTRAIT:
            return img_path

    # Fallback: return first image
    return image_files[0] if image_files else None
