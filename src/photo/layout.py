"""Layout detection for photo pages."""

from ..models import Photo
from .ratio import PhotoRatio, get_photo_ratio

__all__ = ["_is_one_portrait_two_landscapes", "_is_three_portraits"]


def _is_three_portraits(combo: tuple[Photo, ...] | list[Photo]) -> bool:
    """Check if a combination of photos consists of three portrait photos.

    Args:
        combo: Tuple or list of exactly 3 Photo objects.

    Returns:
        True if all three photos are portraits, False otherwise.
    """
    if len(combo) != 3:
        return False

    for photo in combo:
        if not photo.width or not photo.height:
            return False
        ratio = get_photo_ratio(photo.width, photo.height)
        if ratio != PhotoRatio.PORTRAIT:
            return False

    return True


def _is_one_portrait_two_landscapes(combo: tuple[Photo, ...] | list[Photo]) -> bool:
    """Check if a combination consists of one portrait and two landscape photos.

    Args:
        combo: Tuple or list of exactly 3 Photo objects.

    Returns:
        True if the combination is one portrait and two landscapes, False otherwise.
    """
    if len(combo) != 3:
        return False

    ratios = []
    for photo in combo:
        if not photo.width or not photo.height:
            return False
        ratios.append(get_photo_ratio(photo.width, photo.height))

    portrait_count = sum(1 for r in ratios if r == PhotoRatio.PORTRAIT)
    landscape_count = sum(1 for r in ratios if r == PhotoRatio.LANDSCAPE)

    return portrait_count == 1 and landscape_count == 2
