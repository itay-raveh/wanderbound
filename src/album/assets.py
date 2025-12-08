"""Asset management and photo page processing for HTML generation."""

import asyncio
import re
import shutil
from pathlib import Path

from src.album.preparation import _clean_description
from src.core.logger import create_progress, get_logger
from src.core.settings import settings
from src.data.models import Photo, PhotoPageData, Step
from src.photos.layout_engine import (
    is_one_portrait_two_landscapes,
    is_three_portraits,
)

logger = get_logger(__name__)


async def copy_image_to_assets(
    image_path: Path, output_dir: Path, step_name: str, photo_index: int
) -> str:
    images_dir = output_dir / settings.file.assets_dir / settings.file.images_dir
    images_dir.mkdir(parents=True, exist_ok=True)

    sanitized_name = _sanitize_filename(step_name)

    ext = image_path.suffix.lower() or ".jpg"
    output_filename = f"{sanitized_name}_photo_{photo_index}{ext}"
    output_path = images_dir / output_filename

    if not output_path.exists() and image_path.exists():
        await asyncio.to_thread(shutil.copy2, image_path, output_path)

    return f"{settings.file.assets_dir}/{settings.file.images_dir}/{output_filename}"


async def copy_photo_pages(
    photo_pages: list[list[Photo]],
    step_name: str,
    output_dir: Path,
) -> list[PhotoPageData]:
    photo_pages_paths: list[PhotoPageData] = []

    for page in photo_pages:
        # Create tasks for all photos in the page
        copy_tasks = [
            copy_image_to_assets(p.path, output_dir, step_name, p.index)
            for p in page
            if p.path.exists()
        ]

        if not copy_tasks:
            continue

        page_paths = await asyncio.gather(*copy_tasks)

        if page_paths:
            # Calculate layout flags on-the-fly based on photo aspect ratios
            layout_class = None
            grid_style = None

            if len(page) == 3:
                if is_three_portraits(tuple(page)):
                    layout_class = "three-portraits"
                elif is_one_portrait_two_landscapes(tuple(page)):
                    layout_class = "portrait-landscape-split"

                    # Calculate dynamic grid split accounting for row gap
                    # Constants from CSS
                    page_content_width_mm = 272  # 297mm (A4) - 20mm (padding) - 5mm (col gap)
                    row_gap_mm = 7

                    # Get aspect ratios
                    # Clamp portrait AR to minimum 0.75 (3:4) to prevent extremely narrow columns
                    # that cause misalignment for phone screenshots or cropped images.
                    raw_ar_p = page[0].aspect_ratio or 0.75
                    ar_p = max(raw_ar_p, 0.75)
                    ar_l1 = page[1].aspect_ratio or 1.33  # Default to 4:3
                    ar_l2 = page[2].aspect_ratio or 1.33
                    ar_l_avg = (ar_l1 + ar_l2) / 2

                    # Formula derived to ensure:
                    # Height(Left) = Height(Right_Top) + Gap + Height(Right_Bottom)
                    # W_p / AR_p = (W_l / AR_l) + Gap + (W_l / AR_l)
                    # W_p / AR_p = (2 * W_l / AR_l) + Gap
                    # We also know: W_p + W_l = PAGE_CONTENT_WIDTH_MM
                    # ... solving for W_p (P_p) ...

                    numerator = (2 * page_content_width_mm / ar_l_avg) + row_gap_mm
                    denominator = (1 / ar_p) + (2 / ar_l_avg)

                    w_p = numerator / denominator
                    w_l = page_content_width_mm - w_p

                    grid_style = f"grid-template-columns: {w_p:.2f}fr {w_l:.2f}fr;"

            photo_pages_paths.append(
                PhotoPageData(
                    photos=list(page_paths),
                    layout_class=layout_class,
                    grid_style=grid_style,
                )
            )

    return photo_pages_paths


async def copy_cover_images(
    steps: list[Step],
    steps_cover_photos: dict[int, Photo | None],
    output_dir: Path,
) -> list[str | None]:
    logger.debug("Copying cover images to assets...")
    image_progress = create_progress()

    async def _process_cover_image(step: Step) -> str | None:
        cover_photo = steps_cover_photos.get(step.id) if step.id else None
        description = _clean_description(step.description or "")
        # Using module-level settings
        use_three_columns = len(description) > settings.description_three_columns_threshold
        (len(description) > settings.description_two_columns_threshold or use_three_columns)
        # Always copy the cover photo if it exists, so it's available for the map
        # independent of the step page layout.
        if cover_photo and cover_photo.path.exists():
            step_name = step.get_name_for_photos_export()
            try:
                return await copy_image_to_assets(
                    cover_photo.path,
                    output_dir,
                    step_name,
                    cover_photo.index,
                )
            except (OSError, ValueError, AttributeError) as e:
                logger.warning("Failed to process cover image for step %s: %s", step.id, e)
                return None
        return None

    with image_progress:
        task_id = image_progress.add_task("Processing images", total=len(steps))

        # Let's redo with gather but wrapped for progress
        async def _process_with_progress(step: Step) -> str | None:
            res = await _process_cover_image(step)
            image_progress.advance(task_id)
            return res

        tasks = [_process_with_progress(step) for step in steps]
        cover_image_path_list = await asyncio.gather(*tasks)

    logger.debug("Processed %d cover images", len(cover_image_path_list))
    return list(cover_image_path_list)


def _sanitize_filename(name: str) -> str:
    sanitized = re.sub(r"[^\w\-]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip("_")
