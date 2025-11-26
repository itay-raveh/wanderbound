"""Legacy wrapper module for photo selection and management.

This module re-exports functions from the photo submodules for backward compatibility.
New code should import directly from the photo submodules:
- photo.ratio: PhotoRatio, get_photo_ratio
- photo.loader: load_step_photos
- photo.cover: should_use_cover_photo, select_cover_photo
- photo.layout: _is_three_portraits, _is_one_portrait_two_landscapes
- photo.scorer: compute_default_photos_by_pages
"""

from pathlib import Path

from .photo.cover import select_cover_photo, should_use_cover_photo
from .photo.layout import _is_one_portrait_two_landscapes, _is_three_portraits
from .photo.loader import load_step_photos
from .photo.ratio import PhotoRatio, get_photo_ratio
from .photo.scorer import compute_default_photos_by_pages

__all__ = [
    "PhotoRatio",
    "get_photo_ratio",
    "load_step_photos",
    "should_use_cover_photo",
    "select_cover_photo",
    "compute_default_photos_by_pages",
    "select_step_image",
    "_is_three_portraits",
    "_is_one_portrait_two_landscapes",
]


def select_step_image(photo_dir: Path) -> Path | None:
    """Select the best image for a step based on aspect ratio (legacy function).

    This function is kept for backward compatibility. New code should use
    load_step_photos() and select_cover_photo() instead.

    Args:
        photo_dir: Directory containing photos

    Returns:
        Path to selected image, or None if no suitable image found
    """
    photos = load_step_photos(photo_dir)
    cover_photo = select_cover_photo(photos)
    return cover_photo.path if cover_photo else None
