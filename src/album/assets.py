"""Asset management and photo page processing for HTML generation."""

import shutil
from pathlib import Path

from src.core.logger import get_logger
from src.core.settings import settings
from src.core.types import PhotoPageData
from src.data.models import Photo
from src.photos.layout_engine import (
    is_one_portrait_two_landscapes,
    is_three_portraits,
)
from src.utils.files import sanitize_filename
from src.utils.paths import get_assets_path, get_font_path

logger = get_logger(__name__)

__all__ = ["copy_assets", "copy_image_to_assets", "process_photo_pages"]


def copy_image_to_assets(
    image_path: Path, output_dir: Path, step_name: str, photo_index: int
) -> str:
    images_dir = get_assets_path(output_dir, settings.file.images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    sanitized_name = sanitize_filename(step_name)

    ext = image_path.suffix.lower() or ".jpg"
    output_filename = f"{sanitized_name}_photo_{photo_index}{ext}"
    output_path = images_dir / output_filename

    if not output_path.exists() and image_path.exists():
        shutil.copy2(image_path, output_path)

    return f"{settings.file.assets_dir}/{settings.file.images_dir}/{output_filename}"


def copy_assets(output_dir: Path) -> None:
    assets_dir = output_dir / settings.file.assets_dir
    fonts_dir = assets_dir / settings.file.fonts_dir
    css_dir = assets_dir / settings.file.css_dir
    fonts_dir.mkdir(parents=True, exist_ok=True)
    css_dir.mkdir(parents=True, exist_ok=True)

    font_path = get_font_path()
    output_font = fonts_dir / settings.file.font_file
    if not output_font.exists() and font_path.exists():
        shutil.copy2(font_path, output_font)

    # Note: This path might need adjustment depending on where this file is located
    # relative to static dir
    # Current location: src/album/assets.py
    # Project root: ../../../
    # Static dir: ../../../static
    project_root = Path(__file__).parent.parent.parent.parent
    static_dir = project_root / settings.file.static_dir / settings.file.css_dir

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


def process_photo_pages(
    photo_pages: list[list[Photo]],
    step_name: str,
    output_dir: Path,
) -> list[PhotoPageData]:
    photo_pages_paths: list[PhotoPageData] = []

    for page in photo_pages:
        page_paths: list[str] = [
            copy_image_to_assets(photo.path, output_dir, step_name, photo.index)
            for photo in page
            if photo.path.exists()
        ]

        if page_paths:
            # Calculate layout flags on-the-fly based on photo aspect ratios
            three_portraits = False
            portrait_landscape_split = False

            if len(page) == 3:
                if is_three_portraits(tuple(page)):
                    three_portraits = True
                    portrait_landscape_split = False
                elif is_one_portrait_two_landscapes(tuple(page)):
                    three_portraits = False
                    portrait_landscape_split = True

            photo_pages_paths.append(
                PhotoPageData(
                    photos=page_paths,
                    is_three_portraits=three_portraits,
                    is_portrait_landscape_split=portrait_landscape_split,
                )
            )

    return photo_pages_paths
