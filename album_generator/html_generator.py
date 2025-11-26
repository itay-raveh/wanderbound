"""Generate HTML pages for the photo album using Jinja templates."""

from pathlib import Path

from .html.asset_management import copy_assets, copy_image_to_assets
from .html.batch_fetching import (
    fetch_altitudes,
    fetch_flags_batch,
    fetch_maps_batch,
    fetch_weather_data_batch,
    process_cover_images_batch,
)
from .html.step_data_preparation import prepare_step_data
from .logger import create_progress, get_console, get_logger
from .models import Photo, Step, TripData
from .settings import get_settings
from .template_renderer import create_template_environment, render_album_template
from .types import PhotoPageData, StepData

logger = get_logger(__name__)
console = get_console()


def generate_album_html(
    steps: list[Step],
    steps_with_photos: dict[int, list[Photo]],
    steps_cover_photos: dict[int, Photo | None],
    steps_photo_pages: dict[int, list[list[Photo]]],
    steps_photo_page_layouts: dict[int, list[bool]],
    steps_photo_page_portrait_split_layouts: dict[int, list[bool]],
    trip_data: TripData,
    font_path: Path,
    output_path: Path,
    use_step_range: bool = False,
    light_mode: bool = False,
) -> Path:
    """Generate HTML album file from trip data and photos.

    Args:
        steps: List of steps to include in the album
        steps_with_photos: Dictionary mapping step IDs to lists of Photo objects
        steps_cover_photos: Dictionary mapping step IDs to cover Photo (or None)
        steps_photo_pages: Dictionary mapping step IDs to lists of photo pages (each page is a list of Photos)
        steps_photo_page_layouts: Dictionary mapping step IDs to lists of layout flags (True for 3-portrait layout)
        steps_photo_page_portrait_split_layouts: Dictionary mapping step IDs to lists of layout flags (True for portrait-landscape split layout)
        trip_data: Trip metadata including start/end dates, timezone, and all steps
        font_path: Path to the font file to use for titles
        output_path: Path where the HTML file should be written
        use_step_range: If True, progress bars use step range (1 to len(steps));
                       if False, progress bars use trip days from start_date
        light_mode: If True, use light mode color scheme; if False, use dark mode

    Returns:
        Path to the generated HTML file
    """
    copy_assets(font_path, output_path.parent)

    # Batch fetch all external data in parallel
    elevations = fetch_altitudes(steps)
    weather_data_list = fetch_weather_data_batch(steps)
    flag_data_list = fetch_flags_batch(steps, light_mode)
    map_data_list = fetch_maps_batch(steps)
    cover_image_path_list = process_cover_images_batch(
        steps, steps_cover_photos, output_path.parent
    )

    # Prepare template environment
    env = create_template_environment()
    settings = get_settings()
    template = env.get_template(settings.file.album_html_file)

    # Prepare step data
    logger.debug("Preparing step data...")
    step_data_list: list[StepData] = []

    progress = create_progress("Preparing steps")

    with progress:
        task_id = progress.add_task("Preparing steps", total=len(steps))
        for idx, (
            step,
            elevation,
            weather_data,
            flag_data,
            map_data,
            cover_image_path,
        ) in enumerate(
            progress.track(
                zip(
                    steps,
                    elevations,
                    weather_data_list,
                    flag_data_list,
                    map_data_list,
                    cover_image_path_list,
                    strict=True,
                ),
                task_id=task_id,
            )
        ):
            logger.debug(f"Processing step {idx + 1}/{len(steps)}: {step.city}")
            progress.update(task_id, description=f"Preparing steps: {step.city}")

            # Skip steps with missing weather data
            if weather_data is None:
                logger.warning(f"Skipping step {idx} ({step.city}) due to missing weather data")
                continue

            cover_photo = steps_cover_photos.get(step.id) if step.id else None
            photo_pages = steps_photo_pages.get(step.id, []) if step.id else []
            photo_page_layouts = steps_photo_page_layouts.get(step.id, []) if step.id else []
            photo_page_portrait_split_layouts = (
                steps_photo_page_portrait_split_layouts.get(step.id, []) if step.id else []
            )

            # Copy photo pages images to assets directory
            photo_pages_paths: list[PhotoPageData] = []
            step_name = step.get_name_for_photos_export()
            for page_idx, page in enumerate(photo_pages):
                page_paths: list[str] = []
                for photo in page:
                    if photo.path.exists():
                        page_paths.append(
                            copy_image_to_assets(
                                photo.path, output_path.parent, step_name, photo.index
                            )
                        )
                if page_paths:
                    # Get the layout flags for this page
                    # photo_page_layouts should have the same length as photo_pages
                    is_three_portraits = False
                    is_portrait_landscape_split = False
                    if page_idx < len(photo_page_layouts):
                        is_three_portraits = photo_page_layouts[page_idx]
                    if page_idx < len(photo_page_portrait_split_layouts):
                        is_portrait_landscape_split = photo_page_portrait_split_layouts[page_idx]

                    # Safety check: if we have exactly 3 photos, double-check the layout
                    # This ensures the flag is set even if there was a mismatch in the layout array
                    if len(page) == 3:
                        from .image_selector import get_photo_ratio
                        from .photo.layout import (
                            _is_one_portrait_two_landscapes,
                            _is_three_portraits,
                        )

                        if _is_three_portraits(tuple(page)):
                            is_three_portraits = True
                            is_portrait_landscape_split = False
                            logger.debug(
                                f"Detected 3 portraits in html_generator, forcing layout for step {step.id} page {page_idx}"
                            )
                        elif _is_one_portrait_two_landscapes(tuple(page)):
                            is_three_portraits = False
                            is_portrait_landscape_split = True
                            logger.debug(
                                f"Detected 1 portrait + 2 landscapes in html_generator, forcing split layout for step {step.id} page {page_idx}"
                            )
                        else:
                            # Check what we actually have
                            ratios = [get_photo_ratio(p.width or 0, p.height or 0) for p in page]
                            logger.debug(
                                f"Page with 3 photos but no special layout in html_generator. Step {step.id} page {page_idx}, "
                                f"ratios: {[r.name for r in ratios]}, dimensions: {[(p.width, p.height) for p in page]}"
                            )

                    photo_pages_paths.append(
                        PhotoPageData(
                            photos=page_paths,
                            is_three_portraits=is_three_portraits,
                            is_portrait_landscape_split=is_portrait_landscape_split,
                        )
                    )

            step_data = prepare_step_data(
                step,
                cover_photo,
                idx,
                steps,
                trip_data,
                use_step_range,
                elevation,
                weather_data,
                flag_data,
                map_data,
                cover_image_path,
                light_mode,
            )
            # Add photo pages to step data
            step_data["photo_pages"] = photo_pages_paths
            step_data_list.append(step_data)

        progress.update(task_id, description="Preparing steps")

    logger.debug("Step data prepared")

    # Render template
    html = render_album_template(template, step_data_list, light_mode)

    # Write to file
    output_path.write_text(html, encoding="utf-8")

    return output_path
