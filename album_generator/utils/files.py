"""File and filename utility functions."""

import re


def sanitize_filename(name: str) -> str:
    """Sanitize a name for use as a filename.

    Replaces spaces, parentheses, colons, and other special characters
    with underscores, collapses multiple underscores, and removes
    leading/trailing underscores.

    Args:
        name: Original name to sanitize

    Returns:
        Sanitized filename-safe string
    """
    sanitized = re.sub(r"[^\w\-]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip("_")
