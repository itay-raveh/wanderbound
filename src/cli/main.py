"""Main CLI application for generating photo albums."""

import os
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.album.generator import generate_album_html
from src.core.exceptions import DataLoadError
from src.core.logger import create_progress, get_console, get_logger
from src.core.settings import settings
from src.core.types import AlbumGenerationConfig, AlbumPhotoData
from src.data.loader import load_trip_data
from src.data.models import Step
from src.pdf.generator import generate_pdf
from src.photos.processor import process_step_photos
from src.utils.steps import get_steps_distributed, get_steps_in_range

from .args import parse_args, parse_step_range

if TYPE_CHECKING:
    from src.data.models import Photo

logger = get_logger(__name__)
console = get_console()


def _validate_inputs(args: Any) -> Path:
    """Validate input files and directories.

    Args:
        args: Parsed command-line arguments

    Returns:
        Path to trip.json file
    """
    trip_json = Path(args.trip_dir) / "trip.json"
    if not trip_json.exists():
        raise DataLoadError(
            f"trip.json not found at {trip_json}. "
            f"Please ensure the trip directory contains trip.json",
            file_path=str(trip_json),
        )
    return trip_json


def _filter_steps(all_steps: list[Step], args: Any) -> list[Step]:
    """Filter steps based on CLI arguments.

    Args:
        all_steps: All available steps
        args: Parsed command-line arguments

    Returns:
        Filtered list of steps
    """
    if args.sample:
        steps = get_steps_distributed(all_steps, args.sample)
        logger.info("Sampled %d steps evenly across the trip", len(steps))
        return steps
    if args.steps:
        start, end = parse_step_range(args.steps)
        steps = get_steps_in_range(all_steps, start, end)
        logger.info("Filtered to steps %d-%d: %d steps", start, end, len(steps))
        return steps
    logger.info("Using all %d steps", len(all_steps))
    return all_steps


def _load_step_photos(
    steps: list[Step], trip_dir: Path
) -> tuple[dict[int, list["Photo"]], dict[int, "Photo | None"], dict[int, list[list["Photo"]]]]:
    """Load and process photos for all steps.

    Args:
        steps: List of steps to process
        trip_dir: Trip directory path

    Returns:
        Tuple of (steps_with_photos, steps_cover_photos, steps_photo_pages)
    """
    steps_with_photos: dict[int, list[Photo]] = {}
    steps_cover_photos: dict[int, Photo | None] = {}
    steps_photo_pages: dict[int, list[list[Photo]]] = {}

    progress = create_progress("Loading photos")
    with progress:
        task_id = progress.add_task("Loading photos", total=len(steps))
        for step in progress.track(steps, task_id=task_id, description="Loading photos"):
            logger.debug("Loading photos for step: %s", step.city)
            with console.status(f"[bold blue]Processing photos: {step.city}"):
                photos, cover_photo, photo_pages = process_step_photos(step, trip_dir)
            steps_with_photos[step.id] = photos
            steps_cover_photos[step.id] = cover_photo
            steps_photo_pages[step.id] = photo_pages
    return steps_with_photos, steps_cover_photos, steps_photo_pages


def _generate_html_album(
    steps: list[Step],
    photo_data: AlbumPhotoData,
    config: AlbumGenerationConfig,
    *,
    use_step_range: bool,
    light_mode: bool,
) -> Path:
    """Generate HTML album file.

    Args:
        steps: List of steps to include
        photo_data: Dictionary containing steps_with_photos, steps_cover_photos,
            and steps_photo_pages
        config: Configuration dictionary with trip_data and output_dir
        use_step_range: Whether to use step range for progress
        light_mode: Whether to use light mode

    Returns:
        Path to generated HTML file
    """
    with console.status("[bold blue]Generating album HTML..."):
        logger.debug("Generating album HTML...")
        html_path = generate_album_html(
            steps,
            photo_data,
            config,
            use_step_range=use_step_range,
            light_mode=light_mode,
        )
    logger.info("Generated: %s", html_path, extra={"success": True})
    return html_path


def _open_file(file_path: Path, file_type: str) -> None:
    """Open file with default application.

    Args:
        file_path: Path to file to open
        file_type: Type of file ("PDF" or "HTML")
    """
    try:
        wayland_display = os.environ.pop("WAYLAND_DISPLAY", None)
        webbrowser.open(f"file://{file_path.absolute()}")
        if wayland_display:
            os.environ["WAYLAND_DISPLAY"] = wayland_display
        logger.info("Opened %s in default application", file_type, extra={"success": True})
    except (OSError, webbrowser.Error) as e:
        logger.warning("Failed to open %s: %s", file_type, e)


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
    trip_json = _validate_inputs(args)

    with console.status("[bold blue]Loading trip data..."):
        logger.debug("Loading trip data from %s", trip_json)
        trip_data = load_trip_data(trip_json)
        logger.debug("Trip data loaded successfully")

    all_steps = trip_data.all_steps
    if not all_steps:
        raise DataLoadError(
            f"No steps found in trip data. Please check that {trip_json} contains valid step data.",
            file_path=str(trip_json),
        )

    logger.info("Found %d total steps", len(all_steps))
    steps = _filter_steps(all_steps, args)

    args.output.mkdir(parents=True, exist_ok=True)
    logger.debug("Output directory: %s", args.output)

    steps_with_photos, steps_cover_photos, steps_photo_pages = _load_step_photos(
        steps, args.trip_dir
    )

    use_step_range = args.progress_mode == "step-range"
    photo_data: AlbumPhotoData = {
        "steps_with_photos": steps_with_photos,
        "steps_cover_photos": steps_cover_photos,
        "steps_photo_pages": steps_photo_pages,
    }
    album_config: AlbumGenerationConfig = {
        "trip_data": trip_data,
        "output_dir": args.output,
    }
    html_path = _generate_html_album(
        steps,
        photo_data,
        album_config,
        use_step_range=use_step_range,
        light_mode=args.light_mode,
    )

    if args.pdf:
        # Using module-level settings
        pdf_path = args.output / settings.file.album_pdf_file
        with console.status("[bold blue]Generating PDF..."):
            generate_pdf(html_path, pdf_path)
        logger.info("Generated: %s", pdf_path, extra={"success": True})
        if not args.no_open:
            _open_file(pdf_path, "PDF")
    else:
        logger.info("Album generated successfully!", extra={"success": True})
        if not args.no_open:
            _open_file(html_path, "HTML")


if __name__ == "__main__":
    main()
