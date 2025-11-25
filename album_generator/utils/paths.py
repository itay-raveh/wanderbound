"""Path utility functions."""

from pathlib import Path

from ..settings import get_settings


def get_font_path() -> Path:
    """Get the path to the font file (internal to package).

    Returns:
        Path to the Renner.ttf font file
    """
    settings = get_settings()
    return Path(__file__).parent.parent / settings.file.static_dir / settings.file.font_file


def get_assets_path(output_dir: Path, subdir: str) -> Path:
    """Get path to an assets subdirectory.

    Args:
        output_dir: Base output directory
        subdir: Subdirectory name (e.g., 'images', 'fonts', 'css')

    Returns:
        Path to the assets subdirectory
    """
    settings = get_settings()
    return output_dir / settings.file.assets_dir / subdir
