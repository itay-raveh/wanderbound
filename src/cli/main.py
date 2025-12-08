"""Main CLI application for generating photo albums."""

from __future__ import annotations

import asyncio
import os
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

from rich import get_console

from src.album.generator import generate_album_html
from src.core.cache import clear_cache
from src.core.dates import get_display_date_range
from src.core.logger import create_progress, get_logger
from src.core.settings import settings
from src.core.text import is_hebrew
from src.data.locations import LocationEntry, detect_segments, load_locations
from src.data.models import (
    AlbumGenerationConfig,
    AlbumPhotoData,
    Step,
    TripData,
    TripDisplayData,
)
from src.photos.processor import process_step_photos

from .args import Args
from .steps import filter_steps

if TYPE_CHECKING:
    from src.data.models import Photo, Step

logger = get_logger(__name__)


def _load_step_photos(
    steps: list[Step], trip_dir: Path
) -> tuple[dict[int, list[Photo]], dict[int, Photo | None], dict[int, list[list[Photo]]]]:
    steps_with_photos: dict[int, list[Photo]] = {}
    steps_cover_photos: dict[int, Photo | None] = {}
    steps_photo_pages: dict[int, list[list[Photo]]] = {}

    progress = create_progress()
    with progress:
        task_id = progress.add_task("Loading photos", total=len(steps))
        for step in progress.track(steps, task_id=task_id, description="Loading photos"):
            logger.debug("Loading photos for step: %s", step.city)
            with get_console().status(f"[bold blue]Processing photos: {step.city}"):
                photos, cover_photo, photo_pages = process_step_photos(step, trip_dir)
            steps_with_photos[step.id] = photos
            steps_cover_photos[step.id] = cover_photo
            steps_photo_pages[step.id] = photo_pages
    return steps_with_photos, steps_cover_photos, steps_photo_pages


async def _generate_html_album(
    steps: list[Step],
    photo_data: AlbumPhotoData,
    config: AlbumGenerationConfig,
    *,
    use_step_range: bool,
    light_mode: bool,
) -> Path:
    with get_console().status("[bold blue]Generating album HTML..."):
        logger.debug("Generating album HTML...")
        html_path = await generate_album_html(
            steps,
            photo_data,
            config,
            use_step_range=use_step_range,
            light_mode=light_mode,
        )
    logger.info("Generated: %s", html_path, extra={"success": True})
    return html_path


def _open_file(file_path: Path, file_type: str) -> None:
    try:
        wayland_display = os.environ.pop("WAYLAND_DISPLAY", None)
        webbrowser.open(f"file://{file_path.absolute()}")
        if wayland_display:
            os.environ["WAYLAND_DISPLAY"] = wayland_display
        logger.info("Opened %s in default application", file_type, extra={"success": True})
    except (OSError, webbrowser.Error) as e:
        logger.warning("Failed to open %s: %s", file_type, e)


def _generate_pdf(html_path: Path, pdf_path: Path) -> None:
    """Generate PDF file from HTML using Playwright.

    Opens the HTML file in a headless Chromium browser and exports it as a PDF
    with A4 landscape format. Requires Playwright to be installed.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        logger.info("Generating PDF from HTML...")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{html_path.absolute()}")
            page.wait_for_load_state("networkidle")
            # Using module-level settings
            page.set_viewport_size(
                {
                    "width": settings.pdf.viewport_width,
                    "height": settings.pdf.viewport_height,
                }
            )

            page.pdf(
                path=str(pdf_path),
                format="A4",
                landscape=True,
                print_background=True,
                prefer_css_page_size=True,
            )
            browser.close()
        logger.info("PDF generated: %s", pdf_path, extra={"success": True})
    except ImportError:
        logger.warning("Playwright not installed. Install with: playwright install chromium")
        logger.info("Skipping PDF generation.")
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to generate PDF: %s", e)  # noqa: TRY400
        logger.info("You can still open the HTML file in your browser and print to PDF manually.")


def resolve_cover_photo_path(trip_data: TripData, args: Args) -> str | None:
    """Resolve the cover photo path based on priority: CLI -> Local -> URL."""
    # 1. CLI Override
    if args.cover_photo:
        return str(args.cover_photo.absolute())

    if not trip_data.cover_photo:
        return None

    # 2. Local File Search
    if trip_data.cover_photo.uuid:
        uuid = trip_data.cover_photo.uuid
        # Search for the file in trip_dir
        found_photos = list(Path(args.trip_dir).rglob(f"*{uuid}*.jpg"))
        if not found_photos:
            found_photos = list(Path(args.trip_dir).rglob(f"*{uuid}*.jpg.jpg"))

        if found_photos:
            return str(found_photos[0].absolute())

    # 3. Remote URL
    return trip_data.cover_photo.url


def _process_locations(trip_dir: Path, steps: list[Step] | None) -> list[LocationEntry]:
    """Load and process locations.json data."""
    locations_path = trip_dir / "locations.json"

    start_time = None
    end_time = None

    if steps:
        start_time = steps[0].start_time
        end_time = steps[-1].end_time or steps[-1].start_time + 86400

    return load_locations(locations_path, min_time=start_time, max_time=end_time)


def main() -> None:
    args = Args(underscores_to_dashes=True).parse_args()

    trip_json_path = Path(args.trip_dir) / "trip.json"
    if not trip_json_path.exists():
        logger.error(
            "trip.json not found at %s. Please ensure the trip directory contains trip.json",
            trip_json_path,
        )
        return

    logger.info("Found trip.json at %s", trip_json_path)

    if args.no_cache:
        logger.info("Clearing cache as requested...")
        asyncio.run(clear_cache())

    with get_console().status("[bold blue]Loading trip data..."):
        logger.debug("Loading trip data from %s", trip_json_path)
        trip_data = TripData.model_validate_json(
            trip_json_path.read_text(encoding="utf-8"),
        )

        logger.debug("Trip data loaded successfully")

    if not trip_data.all_steps:
        logger.error("No steps found in trip data")
        return

    logger.info("Found %d total steps", len(trip_data.all_steps))
    steps = filter_steps(trip_data.all_steps, args)

    # Prepare display data
    display_title = args.title or trip_data.title or trip_data.name
    display_date_range = get_display_date_range(trip_data, steps)
    cover_photo_path = resolve_cover_photo_path(trip_data, args)

    # Process locations.json
    path_points = _process_locations(args.trip_dir, steps)
    path_segments = detect_segments(path_points) if path_points else []

    trip_display = TripDisplayData(
        display_title=display_title,
        display_date_range=display_date_range,
        summary=trip_data.summary,
        cover_photo_path=cover_photo_path,
        title_dir="rtl" if is_hebrew(display_title) else "ltr",
        summary_dir="rtl" if is_hebrew(trip_data.summary or "") else "ltr",
        trip=trip_data,
        path_points=path_points,
        path_segments=path_segments,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    logger.debug("Output directory: %s", args.out)

    # Load photos
    steps_with_photos, steps_cover_photos, steps_photo_pages = _load_step_photos(
        steps, args.trip_dir
    )

    use_step_range = args.progress_mode == "step-range"
    photo_data = AlbumPhotoData(
        steps_with_photos=steps_with_photos,
        steps_cover_photos=steps_cover_photos,
        steps_photo_pages=steps_photo_pages,
    )
    album_config = AlbumGenerationConfig(
        trip_data=trip_data,
        trip_display_data=trip_display,
        output_dir=args.out,
    )
    html_path = asyncio.run(
        _generate_html_album(
            steps,
            photo_data,
            album_config,
            use_step_range=use_step_range,
            light_mode=args.light_mode,
        )
    )

    if args.pdf:
        pdf_path = args.out / settings.file.album_pdf_file
        with get_console().status("[bold blue]Generating PDF..."):
            _generate_pdf(html_path, pdf_path)
        logger.info("Generated: %s", pdf_path, extra={"success": True})
        if not args.no_open:
            _open_file(pdf_path, "PDF")
    else:
        logger.info("Album generated successfully!", extra={"success": True})
        if not args.no_open:
            _open_file(html_path, "HTML")


if __name__ == "__main__":
    main()
