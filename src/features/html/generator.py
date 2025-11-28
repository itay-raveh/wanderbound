"""Generate HTML pages for the photo album using Jinja templates."""

import shutil
from pathlib import Path

from src.core.logger import create_progress, get_console, get_logger
from src.core.settings import settings
from src.core.types import (
    AlbumGenerationConfig,
    AlbumPhotoData,
    StepContext,
    StepData,
    StepExternalData,
)
from src.data.models import Step

from .assets import process_photo_pages
from .batch_fetching import (
    fetch_altitudes,
    fetch_flags_batch,
    fetch_maps_batch,
    fetch_weather_data_batch,
    process_cover_images_batch,
)
from .preparation import prepare_step_data
from .renderer import create_template_environment, render_album_template

logger = get_logger(__name__)
console = get_console()


def generate_album_html(
    steps: list[Step],
    photo_data: AlbumPhotoData,
    config: AlbumGenerationConfig,
    *,
    use_step_range: bool = False,
    light_mode: bool = False,
) -> Path:
    """Generate HTML album file from trip data and photos.

    Args:
        steps: List of steps to include in the album
        photo_data: Dictionary containing steps_with_photos, steps_cover_photos,
            and steps_photo_pages
        config: Configuration dictionary with trip_data and output_dir
        use_step_range: If True, progress bars use step range (1 to len(steps));
                       if False, progress bars use trip days from start_date
        light_mode: If True, use light mode color scheme; if False, use dark mode

    Returns:
        Path to the generated HTML file
    """
    trip_data = config["trip_data"]
    output_dir = Path(config["output_dir"])
    steps_cover_photos = photo_data["steps_cover_photos"]
    steps_photo_pages = photo_data["steps_photo_pages"]

    # Copy entire static folder to output directory
    # From src/html_generator.py: parent=src/, parent.parent=project root
    static_dir = Path(__file__).parent.parent.parent.parent / "static"
    if static_dir.exists():
        # Copy all contents of static/ to output/
        for item in static_dir.iterdir():
            if item.name == "album.html.jinja":
                # Skip template - will be replaced with rendered HTML
                continue
            dest = output_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)

    # Batch fetch all external data in parallel
    elevations = fetch_altitudes(steps)
    weather_data_list = fetch_weather_data_batch(steps)
    flag_data_list = fetch_flags_batch(steps, light_mode=light_mode)
    map_data_list = fetch_maps_batch(steps)
    cover_image_path_list = process_cover_images_batch(steps, steps_cover_photos, output_dir)

    # Prepare template environment
    env = create_template_environment()
    template = env.get_template("album.html.jinja")

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
            logger.debug("Processing step %d/%d: %s", idx + 1, len(steps), step.city)
            progress.update(task_id, description=f"Preparing steps: {step.city}")

            # Skip steps with missing weather data
            if weather_data is None:
                logger.warning("Skipping step %d (%s) due to missing weather data", idx, step.city)
                continue

            steps_cover_photos.get(step.id) if step.id else None
            photo_pages = steps_photo_pages.get(step.id, []) if step.id else []

            # Copy photo pages images to assets directory
            step_name = step.get_name_for_photos_export()
            photo_pages_paths = process_photo_pages(
                photo_pages,
                step_name,
                output_dir,
            )

            external_data: StepExternalData = {
                "elevation": elevation,
                "weather_data": weather_data,
                "flag_data": flag_data,
                "map_data": map_data,
                "cover_image_path": cover_image_path,
            }
            step_context: StepContext = {
                "step": step,
                "step_index": idx,
                "steps": steps,
                "trip_data": trip_data,
            }
            step_data = prepare_step_data(
                step_context,
                external_data,
                use_step_range=use_step_range,
                light_mode=light_mode,
            )
            # Add photo pages to step data
            step_data["photo_pages"] = photo_pages_paths
            step_data_list.append(step_data)

        progress.update(task_id, description="Preparing steps")

    logger.debug("Step data prepared")

    # Render template
    html = render_album_template(template, step_data_list, light_mode=light_mode)

    # Write rendered HTML to output directory (replacing the template)
    # Using module-level settings
    output_path = output_dir / settings.file.album_html_file
    output_path.write_text(html, encoding="utf-8")

    return output_path
