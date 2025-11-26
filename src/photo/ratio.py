"""Photo aspect ratio detection and categorization."""

from enum import Enum

from ..settings import get_settings

__all__ = ["PhotoRatio", "get_photo_ratio"]


class PhotoRatio(Enum):
    """Photo aspect ratio categories."""

    PORTRAIT = [(4, 5), (9, 16), (3, 4)]  # 4:5 (5:4 portrait) is ideal for cover photos
    LANDSCAPE = [(16, 9), (4, 3)]
    UNKNOWN = None  # Sentinel value


def get_photo_ratio(width: int, height: int) -> PhotoRatio:
    """Categorize photo aspect ratio into portrait, landscape, or unknown.

    Compares the photo's aspect ratio against known ratios with tolerance
    to account for slight variations in actual dimensions.

    Args:
        width: Photo width in pixels.
        height: Photo height in pixels.

    Returns:
        PhotoRatio enum value (PORTRAIT, LANDSCAPE, or UNKNOWN).
    """
    settings = get_settings()
    aspect_ratio = width / height if height > 0 else 0

    for photo_ratio in PhotoRatio:
        if photo_ratio == PhotoRatio.UNKNOWN:
            continue
        ratio_list = (
            list(photo_ratio.value) if isinstance(photo_ratio.value, tuple) else photo_ratio.value
        )
        for ratio_tuple in ratio_list:
            ratio_width, ratio_height = ratio_tuple
            target_ratio = ratio_width / ratio_height
            if abs(aspect_ratio - target_ratio) < settings.photo.aspect_ratio_tolerance:
                return photo_ratio

    return PhotoRatio.UNKNOWN
