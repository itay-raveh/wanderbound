"""Main CLI application for generating photo albums."""

import os
import webbrowser

from .cli import parse_args, parse_step_range
from .data_loader import load_trip_data
from .exceptions import DataLoadError
from .html_generator import generate_album_html
from .logger import create_progress, get_console, get_logger
from .models import Photo
from .output.pdf_generator import generate_pdf
from .photo_manager import load_photos_config, save_photos_config
from .photo_processor import process_step_photos
from .settings import get_settings
from .utils.steps import get_steps_distributed, get_steps_in_range

logger = get_logger(__name__)
console = get_console()


def main() -> None:
    """Main entry point for the album generator CLI application.

    Orchestrates the entire album generation process:
    1. Validates input files and directories
    2. Loads trip data from JSON
    3. Filters steps based on CLI arguments
    4. Loads and processes photos for each step
    5. Generates HTML album
    6. Optionally generates PDF

    Raises:
        DataLoadError: If trip.json is missing or invalid.
        ValidationError: If required internal files (e.g., font) are missing.
    """
    args = parse_args()

    # Validate inputs
    trip_json = args.trip_dir / "trip.json"
    if not trip_json.exists():
        raise DataLoadError(
            f"trip.json not found at {trip_json}. "
            f"Please ensure the trip directory contains trip.json",
            file_path=str(trip_json),
        )

    from .utils.paths import get_font_path

    font_path = get_font_path()

    with console.status("[bold blue]Loading trip data..."):
        logger.debug(f"Loading trip data from {trip_json}")
        trip_data = load_trip_data(trip_json)
        logger.debug("Trip data loaded successfully")
    all_steps = trip_data.all_steps

    if not all_steps:
        raise DataLoadError(
            "No steps found in trip data. "
            f"Please check that {trip_json} contains valid step data.",
            file_path=str(trip_json),
        )

    logger.info(f"Found {len(all_steps)} total steps")

    # Filter steps by range or sample
    if args.sample:
        steps = get_steps_distributed(all_steps, args.sample)
        logger.info(f"Sampled {len(steps)} steps evenly across the trip")
    elif args.steps:
        start, end = parse_step_range(args.steps)
        steps = get_steps_in_range(all_steps, start, end)
        logger.info(f"Filtered to steps {start}-{end}: {len(steps)} steps")
    else:
        steps = all_steps
        logger.info(f"Using all {len(steps)} steps")

    args.output.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Output directory: {args.output}")

    # Clear photos cache if requested
    if args.clear_photos_cache:
        logger.info("Clearing photos cache...")
        settings = get_settings()
        photos_config_path = args.output / settings.file.photos_mapping_file
        photos_pages_path = args.output / settings.file.photos_by_pages_file
        if photos_config_path.exists():
            photos_config_path.unlink()
            logger.debug(f"Deleted {photos_config_path}")
        if photos_pages_path.exists():
            photos_pages_path.unlink()
            logger.debug(f"Deleted {photos_pages_path}")

    photo_config = load_photos_config(steps, args.output)
    steps_with_photos: dict[int, list[Photo]] = {}
    steps_cover_photos: dict[int, Photo | None] = {}
    steps_photo_pages: dict[int, list[list[Photo]]] = {}
    steps_photo_page_layouts: dict[int, list[bool]] = {}
    steps_photo_page_portrait_split_layouts: dict[int, list[bool]] = {}

    progress = create_progress("Loading photos")

    with progress:
        task_id = progress.add_task("Loading photos", total=len(steps))
        for step in progress.track(steps, task_id=task_id, description="Loading photos"):
            logger.debug(f"Loading photos for step: {step.city}")

            with console.status(f"[bold blue]Processing photos: {step.city}"):
                (
                    photos,
                    cover_photo,
                    photo_pages,
                    is_three_portraits,
                    is_portrait_landscape_split,
                ) = process_step_photos(step, args.trip_dir, photo_config)

            steps_with_photos[step.id] = photos
            steps_cover_photos[step.id] = cover_photo
            steps_photo_pages[step.id] = photo_pages
            steps_photo_page_layouts[step.id] = is_three_portraits
            steps_photo_page_portrait_split_layouts[step.id] = is_portrait_landscape_split

    # Save photo configuration for manual editing
    save_photos_config(
        steps,
        steps_with_photos,
        steps_cover_photos,
        steps_photo_pages,
        args.output,
        steps_photo_page_layouts,
        steps_photo_page_portrait_split_layouts,
    )

    # Generate single HTML file with all steps
    settings = get_settings()
    html_path = args.output / settings.file.album_html_file
    use_step_range = args.progress_mode == "step-range"
    with console.status("[bold blue]Generating album HTML..."):
        logger.debug("Generating album HTML...")
        generate_album_html(
            steps,
            steps_with_photos,
            steps_cover_photos,
            steps_photo_pages,
            steps_photo_page_layouts,
            steps_photo_page_portrait_split_layouts,
            trip_data,
            font_path,
            html_path,
            use_step_range,
            args.light_mode,
        )
    logger.info(f"Generated: {html_path}", extra={"success": True})

    # Generate PDF if requested
    if args.pdf:
        settings = get_settings()
        pdf_path = args.output / settings.file.album_pdf_file
        with console.status("[bold blue]Generating PDF..."):
            generate_pdf(html_path, pdf_path)
        logger.info(f"Generated: {pdf_path}", extra={"success": True})
        file_to_open = pdf_path
    else:
        logger.info("Album generated successfully!", extra={"success": True})
        file_to_open = html_path

    # Open file with default application
    # Suppress Wayland display warnings on Linux (webbrowser will fallback to X11)
    try:
        wayland_display = os.environ.pop("WAYLAND_DISPLAY", None)
        webbrowser.open(f"file://{file_to_open.absolute()}")
        if wayland_display:
            os.environ["WAYLAND_DISPLAY"] = wayland_display
        file_type = "PDF" if args.pdf else "HTML"
        logger.info(f"Opened {file_type} in default application", extra={"success": True})
    except Exception as e:
        file_type = "PDF" if args.pdf else "HTML"
        logger.warning(f"Failed to open {file_type}: {e}")


if __name__ == "__main__":
    main()
