"""Asset management and photo page processing for HTML generation."""

import shutil
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

from src.album.preparation import _clean_description
from src.core.logger import create_progress, get_logger
from src.core.settings import settings
from src.core.types import PhotoPageData
from src.data.models import Photo, Step
from src.photos.layout_engine import (
    is_one_portrait_two_landscapes,
    is_three_portraits,
)
from src.utils.files import sanitize_filename
from src.utils.paths import get_assets_path, get_font_path

logger = get_logger(__name__)

__all__ = [
    "copy_assets",
    "copy_cover_images",
    "copy_image_to_assets",
    "copy_photo_pages",
]


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


def copy_photo_pages(
    photo_pages: list[list[Photo]],
    step_name: str,
    output_dir: Path,
) -> list[PhotoPageData]:
    photo_pages_paths: list[PhotoPageData] = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        for page in photo_pages:
            # Submit copy tasks for all photos in the page
            page_paths = list(
                executor.map(
                    lambda p: copy_image_to_assets(p.path, output_dir, step_name, p.index),
                    [p for p in page if p.path.exists()],
                )
            )

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


def copy_cover_images(
    steps: list[Step],
    steps_cover_photos: dict[int, Photo | None],
    output_dir: Path,
) -> list[str | None]:
    logger.debug("Copying cover images to assets...")
    image_progress = create_progress("Processing images")
    cover_image_path_list: list[str | None] = [None] * len(steps)

    def _process_cover_image(step: Step) -> str | None:
        cover_photo = steps_cover_photos.get(step.id) if step.id else None
        description = _clean_description(step.description or "")
        # Using module-level settings
        use_three_columns = len(description) > settings.description_three_columns_threshold
        use_two_columns = (
            len(description) > settings.description_two_columns_threshold or use_three_columns
        )
        if cover_photo and cover_photo.path.exists() and not use_two_columns:
            step_name = step.get_name_for_photos_export()
            return copy_image_to_assets(
                cover_photo.path,
                output_dir,
                step_name,
                cover_photo.index,
            )
        return None

    with image_progress:
        task_id = image_progress.add_task("Processing images", total=len(steps))
        with ThreadPoolExecutor(max_workers=5) as image_executor:
            image_future_to_index: dict[Future[str | None], int] = {
                image_executor.submit(_process_cover_image, step): idx
                for idx, step in enumerate(steps)
            }
            for future in as_completed(image_future_to_index):
                idx = image_future_to_index[future]
                try:
                    result = future.result()
                    cover_image_path_list[idx] = result
                    image_progress.advance(task_id)
                except (OSError, ValueError, AttributeError) as e:
                    logger.warning("Failed to process cover image for step %d: %s", idx, e)
                    image_progress.advance(task_id)
    logger.debug("Processed %d cover images", len(cover_image_path_list))
    return cover_image_path_list
