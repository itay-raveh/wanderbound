"""Cover photo selection logic."""

from ..models import Photo
from ..settings import get_settings

__all__ = ["should_use_cover_photo", "select_cover_photo"]


def should_use_cover_photo(description: str | None) -> bool:
    """Determine if a step should use a cover photo.

    Cover photos are only used when the description is short enough
    to fit in a single column layout.

    Args:
        description: Step description text.

    Returns:
        True if cover photo should be used, False otherwise.
    """
    if not description:
        return True

    settings = get_settings()
    return len(description) <= settings.description_max_char_cover_photo


def select_cover_photo(photos: list[Photo]) -> Photo | None:
    """Select the best cover photo from a list of photos.

    Prefers portrait photos with 4:5 aspect ratio (ideal for cover photos).
    Falls back to other portrait photos, then landscape photos.

    Args:
        photos: List of Photo objects to choose from.

    Returns:
        Best Photo for cover, or None if no suitable photo found.
    """
    if not photos:
        return None

    from .ratio import PhotoRatio, get_photo_ratio

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
