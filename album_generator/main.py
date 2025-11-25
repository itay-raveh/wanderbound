"""Main CLI application for generating photo albums."""

import os
import webbrowser
from pathlib import Path

from .cli import parse_args
from .data_loader import (
    get_step_photo_dir,
    get_steps_distributed,
    get_steps_in_range,
    load_trip_data,
)
from .exceptions import DataLoadError, ValidationError
from .html_generator import generate_album_html
from .image_selector import (
    compute_default_photos_by_pages,
    load_step_photos,
    select_cover_photo,
    should_use_cover_photo,
)
from .logger import create_progress, get_console, get_logger
from .models import Photo
from .photo_manager import load_photos_config, save_photos_config
from .settings import get_settings

logger = get_logger(__name__)
console = get_console()


def parse_step_range(range_str: str) -> tuple[int, int]:
    """Parse step range string into start and end step numbers.

    Args:
        range_str: Step range string in format "start-end" or single step number.

    Returns:
        Tuple of (start, end) step numbers (1-indexed, inclusive).
        If single number provided, both start and end are the same.

    Examples:
        >>> parse_step_range("99-110")
        (99, 110)
        >>> parse_step_range("99")
        (99, 99)
    """
    if "-" in range_str:
        start, end = range_str.split("-", 1)
        return int(start.strip()), int(end.strip())
    else:
        step_num = int(range_str.strip())
        return step_num, step_num


def generate_pdf(html_path: Path, pdf_path: Path) -> None:
    """Generate PDF file from HTML using Playwright.

    Opens the HTML file in a headless Chromium browser and exports it as a PDF
    with A4 landscape format. Requires Playwright to be installed.

    Args:
        html_path: Path to the input HTML file.
        pdf_path: Path where the PDF file will be saved.

    Raises:
        ImportError: If Playwright is not installed (logged as warning).
        Exception: Any other error during PDF generation (logged as error).
    """
    try:
        from playwright.sync_api import sync_playwright

        logger.info("Generating PDF from HTML...")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{html_path.absolute()}")
            page.wait_for_load_state("networkidle")
            settings = get_settings()
            page.set_viewport_size(
                {"width": settings.pdf.viewport_width, "height": settings.pdf.viewport_height}
            )

            page.pdf(
                path=str(pdf_path),
                format="A4",
                landscape=True,
                print_background=True,
                prefer_css_page_size=True,
            )
            browser.close()
        logger.info(f"PDF generated: {pdf_path}", extra={"success": True})
    except ImportError:
        logger.warning("Playwright not installed. Install with: playwright install chromium")
        logger.info("Skipping PDF generation.")
    except Exception as e:
        logger.error(f"Failed to generate PDF: {e}", exc_info=True)
        logger.info("You can still open the HTML file in your browser and print to PDF manually.")


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
    if not font_path.exists():
        raise ValidationError(
            f"Font file not found at {font_path}. "
            f"This is an internal package file and should always be present.",
            field="font_path",
        )

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
        for step in progress.track(steps, task_id=task_id):
            logger.debug(f"Loading photos for step: {step.city}")
            progress.update(task_id, description=f"Loading photos: {step.city}")

            photo_dir = get_step_photo_dir(args.trip_dir, step)
            if not photo_dir:
                logger.warning(
                    f"No photo directory found for step '{step.city}' (ID: {step.id}). "
                    f"Expected directory pattern: {step.slug or step.display_slug}_{step.id}/photos "
                    f"in {args.trip_dir}"
                )
                steps_with_photos[step.id] = []
                steps_cover_photos[step.id] = None
                steps_photo_pages[step.id] = []
                continue

            photos = load_step_photos(photo_dir)
            steps_with_photos[step.id] = photos

            if not photos:
                logger.warning(
                    f"No photos found in {photo_dir} for step '{step.city}'. "
                    f"Expected image files (.jpg, .jpeg, .png)"
                )
                steps_cover_photos[step.id] = None
                steps_photo_pages[step.id] = []
                continue

            # Determine if we should use cover photo based on description length
            use_cover = should_use_cover_photo(step.description)

            # Check if we have saved configuration for this step
            if photo_config and step.id in photo_config:
                config = photo_config[step.id]
                # Use saved cover photo if available
                cover_photo_index = config.get("cover_photo_index")
                if cover_photo_index:
                    cover_photo = next((p for p in photos if p.index == cover_photo_index), None)
                    steps_cover_photos[step.id] = cover_photo if use_cover else None
                else:
                    steps_cover_photos[step.id] = select_cover_photo(photos) if use_cover else None

                # Use saved photo pages if available
                photo_pages_indices = config.get("photo_pages", [])
                if photo_pages_indices:
                    photo_pages: list[list[Photo]] = []
                    # Create a mapping from photo index to Photo object for quick lookup
                    photos_by_index = {p.index: p for p in photos}
                    for page_indices in photo_pages_indices:
                        # Preserve the order from saved indices
                        page_photos = [
                            photos_by_index[idx] for idx in page_indices if idx in photos_by_index
                        ]
                        if page_photos:
                            photo_pages.append(page_photos)
                    steps_photo_pages[step.id] = photo_pages
                    # Load layout flags
                    saved_is_three_portraits = config.get("is_three_portraits", [])
                    saved_is_portrait_landscape_split = config.get(
                        "is_portrait_landscape_split", []
                    )
                    logger.debug(
                        f"Loading layout flags for step {step.city}: "
                        f"is_three_portraits={saved_is_three_portraits}, "
                        f"is_portrait_landscape_split={saved_is_portrait_landscape_split}, "
                        f"num_pages={len(photo_pages)}"
                    )
                    # Ensure flags match the number of pages, or compute them if missing
                    if len(saved_is_three_portraits) == len(photo_pages):
                        steps_photo_page_layouts[step.id] = saved_is_three_portraits
                        logger.debug(f"Using saved is_three_portraits flags for step {step.city}")
                    else:
                        # Compute flags from photo pages
                        from .image_selector import (
                            _is_one_portrait_two_landscapes,
                            _is_three_portraits,
                        )

                        computed_is_three_portraits: list[bool] = []
                        for page in photo_pages:
                            computed_is_three_portraits.append(
                                len(page) == 3 and _is_three_portraits(tuple(page))
                            )
                        steps_photo_page_layouts[step.id] = computed_is_three_portraits
                        logger.debug(
                            f"Computed is_three_portraits flags for step {step.city}: {computed_is_three_portraits}"
                        )

                    if len(saved_is_portrait_landscape_split) == len(photo_pages):
                        steps_photo_page_portrait_split_layouts[step.id] = (
                            saved_is_portrait_landscape_split
                        )
                        logger.debug(
                            f"Using saved is_portrait_landscape_split flags for step {step.city}: {saved_is_portrait_landscape_split}"
                        )
                    else:
                        # Compute flags from photo pages
                        from .image_selector import _is_one_portrait_two_landscapes

                        computed_is_portrait_landscape_split: list[bool] = []
                        for page in photo_pages:
                            computed_is_portrait_landscape_split.append(
                                len(page) == 3 and _is_one_portrait_two_landscapes(tuple(page))
                            )
                        steps_photo_page_portrait_split_layouts[step.id] = (
                            computed_is_portrait_landscape_split
                        )
                        logger.debug(
                            f"Computed is_portrait_landscape_split flags for step {step.city}: {computed_is_portrait_landscape_split}"
                        )
                else:
                    # Use default layout strategy
                    cover = steps_cover_photos[step.id]
                    with console.status(f"[bold blue]Computing photo layout: {step.city}"):
                        pages, layouts, split_layouts = compute_default_photos_by_pages(
                            photos, cover
                        )
                        steps_photo_pages[step.id] = pages
                        steps_photo_page_layouts[step.id] = layouts
                        steps_photo_page_portrait_split_layouts[step.id] = split_layouts
            else:
                # No saved config: use automatic selection
                cover_photo = select_cover_photo(photos) if use_cover else None
                steps_cover_photos[step.id] = cover_photo
                # Use default layout strategy
                with console.status(f"[bold blue]Computing photo layout: {step.city}"):
                    pages, layouts, split_layouts = compute_default_photos_by_pages(
                        photos, cover_photo
                    )
                    steps_photo_pages[step.id] = pages
                    steps_photo_page_layouts[step.id] = layouts
                    steps_photo_page_portrait_split_layouts[step.id] = split_layouts

        progress.update(task_id, description="Loading photos")

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
