"""Path utility functions."""

from pathlib import Path

from ..models import Step
from ..settings import get_settings

__all__ = ["get_assets_path", "get_font_path", "get_step_photo_dir"]


def get_font_path() -> Path:
    """Get the path to the font file (internal to package).

    Returns:
        Path to the Renner.ttf font file.

    Raises:
        ConfigurationError: If settings cannot be loaded.
    """
    settings = get_settings()
    font_path = Path(__file__).parent.parent / settings.file.static_dir / settings.file.font_file
    if not font_path.exists():
        from ..exceptions import ConfigurationError

        raise ConfigurationError(
            f"Font file not found at {font_path}. "
            f"This is an internal package file and should always be present. "
            f"Please reinstall the package or check your installation."
        )
    return font_path


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


def get_step_photo_dir(trip_dir: Path, step: Step) -> Path | None:
    """Get the photo directory path for a step.

    Searches for photo directories matching common naming patterns:
    - {slug}_{step_id}/photos
    - {display_slug}_{step_id}/photos

    Args:
        trip_dir: Base trip directory containing step folders.
        step: Step object with slug and ID information.

    Returns:
        Path to the photo directory if found, None otherwise.
    """
    slug = step.slug or step.display_slug or ""

    if not slug:
        return None

    # Try both patterns: slug_id and display_slug_id
    patterns = [
        f"{slug}_{step.id}",
        f"{step.display_slug or slug}_{step.id}",
    ]

    for pattern in patterns:
        photo_dir = trip_dir / pattern / "photos"
        if photo_dir.exists():
            return photo_dir

    return None
