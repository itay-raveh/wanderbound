"""File and filename utility functions."""

import re


def sanitize_filename(name: str) -> str:
    sanitized = re.sub(r"[^\w\-]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip("_")
