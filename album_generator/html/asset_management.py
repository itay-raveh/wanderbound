"""Asset management for HTML generation."""

import shutil
from pathlib import Path

from ..settings import get_settings
from ..utils.files import sanitize_filename
from ..utils.paths import get_assets_path

__all__ = ["copy_image_to_assets", "copy_assets"]


def copy_image_to_assets(
    image_path: Path, output_dir: Path, step_name: str, photo_index: int
) -> str:
    """Copy image to assets directory and return relative path.

    Args:
        image_path: Path to source image file
        output_dir: Output directory (parent of assets/)
        step_name: Step name (e.g., "Buenos Aires (Argentina)") - matches photos_by_pages.txt
        photo_index: Photo index within the step (matches photos_by_pages.txt)

    Returns:
        Relative path to copied image (e.g., "assets/images/Buenos_Aires_Argentina_photo_0.jpg")
    """
    settings = get_settings()
    images_dir = get_assets_path(output_dir, settings.file.images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    sanitized_name = sanitize_filename(step_name)

    ext = image_path.suffix.lower() or ".jpg"
    output_filename = f"{sanitized_name}_photo_{photo_index}{ext}"
    output_path = images_dir / output_filename

    if not output_path.exists() and image_path.exists():
        shutil.copy2(image_path, output_path)

    return f"{settings.file.assets_dir}/{settings.file.images_dir}/{output_filename}"


def copy_assets(font_path: Path, output_dir: Path) -> None:
    """Copy assets (fonts, CSS, etc.) to output directory.

    Args:
        font_path: Path to font file to copy
        output_dir: Output directory where assets should be copied
    """
    settings = get_settings()

    assets_dir = output_dir / settings.file.assets_dir
    fonts_dir = assets_dir / settings.file.fonts_dir
    css_dir = assets_dir / settings.file.css_dir
    fonts_dir.mkdir(parents=True, exist_ok=True)
    css_dir.mkdir(parents=True, exist_ok=True)

    output_font = fonts_dir / settings.file.font_file
    if not output_font.exists() and font_path.exists():
        shutil.copy2(font_path, output_font)

    static_dir = Path(__file__).parent.parent / settings.file.static_dir / settings.file.css_dir
    css_files = [
        "variables.css",
        "reset.css",
        "layout.css",
        "components.css",
        "typography.css",
        "photos.css",
    ]

    for css_file in css_files:
        source_css = static_dir / css_file
        output_css = css_dir / css_file
        if source_css.exists():
            shutil.copy2(source_css, output_css)
