"""Generate HTML pages for the photo album using Jinja templates."""

from pathlib import Path

from .html.asset_management import copy_assets
from .html.batch_fetching import (
    fetch_altitudes,
    fetch_flags_batch,
    fetch_maps_batch,
    fetch_weather_data_batch,
    process_cover_images_batch,
)
from .html.photo_pages import process_photo_pages
from .html.step_data_preparation import prepare_step_data
from .logger import create_progress, get_console, get_logger
from .models import Photo, Step, TripData
from .settings import get_settings
from .template_renderer import create_template_environment, render_album_template
from .types import StepData

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
            step_name = step.get_name_for_photos_export()
            photo_pages_paths = process_photo_pages(
                photo_pages,
                photo_page_layouts,
                photo_page_portrait_split_layouts,
                step_name,
                output_path.parent,
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
