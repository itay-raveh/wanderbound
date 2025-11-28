"""Photo layout engine: aspect ratio detection, cover selection, and layout checks."""

from enum import Enum

from src.core.settings import settings
from src.data.models import Photo

__all__ = [
    "PhotoRatio",
    "get_photo_ratio",
    "is_one_portrait_two_landscapes",
    "is_three_portraits",
    "select_cover_photo",
    "should_use_cover_photo",
]


class PhotoRatio(Enum):
    """Photo aspect ratio categories."""

    PORTRAIT = (
        (4, 5),
        (9, 16),
        (3, 4),
    )  # 4:5 (5:4 portrait) is ideal for cover photos
    LANDSCAPE = ((16, 9), (4, 3))
    UNKNOWN = None  # Sentinel value


def get_photo_ratio(width: int, height: int) -> PhotoRatio:
    """Categorize photo aspect ratio into portrait, landscape, or unknown."""
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


def should_use_cover_photo(description: str | None) -> bool:
    """Determine if a step should use a cover photo."""
    if not description:
        return True
    return len(description) <= settings.description_max_char_cover_photo


def select_cover_photo(photos: list[Photo]) -> Photo | None:
    """Select the best cover photo from a list of photos."""
    if not photos:
        return None

    # Prefer 4:5 portrait photos (ideal aspect ratio for cover)
    ideal_portraits = [
        p
        for p in photos
        if p.width
        and p.height
        and get_photo_ratio(p.width, p.height) == PhotoRatio.PORTRAIT
        and abs((p.width / p.height) - (4 / 5)) < 0.1
    ]
    if ideal_portraits:
        return ideal_portraits[0]

    # Fall back to any portrait photos
    portraits = [
        p
        for p in photos
        if p.width and p.height and get_photo_ratio(p.width, p.height) == PhotoRatio.PORTRAIT
    ]
    if portraits:
        return portraits[0]

    # Last resort: use first available photo
    return photos[0]


def is_three_portraits(combo: tuple[Photo, ...] | list[Photo]) -> bool:
    """Check if a combination of photos consists of three portrait photos."""
    if len(combo) != 3:
        return False

    for photo in combo:
        if not photo.width or not photo.height:
            return False
        ratio = get_photo_ratio(photo.width, photo.height)
        if ratio != PhotoRatio.PORTRAIT:
            return False

    return True


def is_one_portrait_two_landscapes(combo: tuple[Photo, ...] | list[Photo]) -> bool:
    """Check if a combination consists of one portrait and two landscape photos."""
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
