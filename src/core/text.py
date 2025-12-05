"""Text utility functions."""


def is_hebrew(text: str) -> bool:
    """Check if text contains Hebrew characters."""
    # https://www.unicode.org/charts/PDF/U0590.pdf
    return any("\u0590" <= char <= "\u05ff" for char in text)
