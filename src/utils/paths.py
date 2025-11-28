"""Path utility functions."""

from pathlib import Path

from src.core.exceptions import ConfigurationError
from src.core.settings import settings
from src.data.models import Step

__all__ = ["get_assets_path", "get_font_path", "get_step_photo_dir"]


def get_font_path() -> Path:
    font_path = (
        Path(__file__).parent.parent.parent / settings.file.static_dir / settings.file.font_file
    )
    if not font_path.exists():
        raise ConfigurationError(
            f"Font file not found at {font_path}. "
            f"This is an internal package file and should always be present. "
            f"Please reinstall the package or check your installation."
        )
    return font_path


def get_assets_path(output_dir: Path, subdir: str) -> Path:
    return output_dir / settings.file.assets_dir / subdir


def get_step_photo_dir(trip_dir: Path, step: Step) -> Path | None:
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
