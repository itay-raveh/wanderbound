"""Image similarity functions using dHash (Difference Hash)."""

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from src.core.logger import get_logger

logger = get_logger(__name__)


def compute_dhash(image: Image.Image, hash_size: int = 8) -> int:
    """Compute the difference hash (dHash) of an image.

    Hash size 8 means an 8x8 hash (64 bits).
    The image is resized to (hash_size + 1, hash_size).
    """
    # Resize to (width, height) = (hash_size + 1, hash_size)
    # Use LANCZOS for best quality downsampling, though for hashing BILINEAR is often enough.
    # We'll use BILINEAR for speed.
    image = image.resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)

    # Convert to grayscale
    image = image.convert("L")

    # Get pixel data
    pixels = np.array(image.getdata(), dtype=np.int8).reshape((hash_size, hash_size + 1))

    # Compute differences between adjacent columns
    diff = pixels[:, :-1] > pixels[:, 1:]

    # Convert to integer
    # Flatten and pack bits
    # This creates a 64-bit integer
    return _bool_array_to_int(diff.flatten())


def _bool_array_to_int(bool_arr: np.ndarray[Any, Any]) -> int:
    """Convert a boolean array to an integer."""
    res = 0
    for b in bool_arr:
        res = (res << 1) | int(b)
    return res


def compute_image_hash(image_path: Path) -> int | None:
    """Load image and compute its hash."""
    try:
        with Image.open(image_path) as img:
            return compute_dhash(img)
    except (OSError, ValueError) as e:
        logger.debug("Failed to compute hash for %s: %s", image_path, e)
        return None


def hamming_distance(hash1: int, hash2: int) -> int:
    """Compute the Hamming distance between two 64-bit integers."""
    # XOR the two hashes, then count set bits (population count)
    x = hash1 ^ hash2
    return x.bit_count()


def are_similar(hash1: int, hash2: int, threshold: int = 5) -> bool:
    """Check if two hashes are similar within the given threshold.

    For 64-bit hashes, a threshold of 5-10 is typical for 'visually similar'.
    Duplicate detection usually uses a low threshold (e.g. 0-2).
    """
    return hamming_distance(hash1, hash2) <= threshold
