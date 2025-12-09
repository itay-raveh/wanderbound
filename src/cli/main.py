"""Main CLI application for generating photo albums."""

from __future__ import annotations

import asyncio
import os
import webbrowser
from datetime import datetime as dt  # noqa: F401
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError
from rich import get_console

from src.album.generator import generate_album_html
from src.cli.edit import EditorServer
from src.core.cache import clear_cache
from src.core.dates import get_display_date_range
from src.core.logger import get_logger
from src.core.settings import settings
from src.core.text import is_hebrew
from src.data.layout import AlbumLayout, PageLayout, StepLayout
from src.data.locations import LocationEntry, _detect_segments, load_locations
from src.data.models import (
    AlbumGenerationConfig,
    AlbumPhotoData,
    Step,
    TripData,
    TripDisplayData,
)
from src.photos.processor import process_step_photos
from src.photos.registry import PhotoRegistry

from .args import Args
from .steps import filter_steps

if TYPE_CHECKING:
    from src.data.models import Step

logger = get_logger(__name__)


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


async def _reload_step_data(
    step_id: int | None,
    all_steps: list[Step],
    trip_dir: Path,
    photo_data: AlbumPhotoData,
    output_dir: Path,
) -> None:
    """Reloads step data, applying any layout overrides from layout.json."""
    logger.info("Reloading layout data...")

    # Reload layout file - Always reload from disk to get latest editor changes
    layout_file = output_dir / "layout.json"
    layout_overrides = AlbumLayout(steps={})

    # We must ensure we don't hold onto stale file handles or cache if possible
    # (Though read_text is atomic enough for this)
    if layout_file.exists():
        try:
            content = layout_file.read_text()
            layout_overrides = AlbumLayout.model_validate_json(content)
        except (ValueError, TypeError, ValidationError) as e:
            logger.warning("Failed to load layout.json: %s", e)

    # Initialize Global Registry if not already done?
    # actually, we need to pass strict trip_dir.
    # We should probably initialize it once in main() and pass it down.
    # But _reload_step_data logic is standalone-ish.

    photo_registry = PhotoRegistry(trip_dir)
    photo_registry.scan()

    # Compute Global Used IDs
    # Iterate all steps in layout_overrides to see what is claimed.
    global_used_ids = set()
    for s_layout in layout_overrides.steps.values():
        if s_layout.cover_photo_id:
            global_used_ids.add(s_layout.cover_photo_id)
        global_used_ids.update(s_layout.hidden_photos)
        for p in s_layout.pages:
            global_used_ids.update(p.photos)

    target_steps = [s for s in all_steps if s.id == step_id] if step_id else all_steps

    for step in target_steps:
        # Check for overrides
        step_layout = layout_overrides.steps.get(step.id)

        # Reprocess photos with overrides
        photos, cover_photo, photo_pages, hidden_photos = process_step_photos(
            step, trip_dir, photo_registry, global_used_ids, layout_override=step_layout
        )

        # Update shared state
        photo_data.steps_with_photos[step.id] = photos
        photo_data.steps_cover_photos[step.id] = cover_photo
        photo_data.steps_photo_pages[step.id] = photo_pages
        photo_data.steps_hidden_photos[step.id] = hidden_photos

    # --- Save Layout JSON ---
    logger.debug("Saving current layout state to layout.json...")

    # Rebuild layout object from processed results to include defaults and overrides
    new_steps = {}

    for s in target_steps:
        cover = photo_data.steps_cover_photos.get(s.id)
        pages = photo_data.steps_photo_pages.get(s.id, [])
        hidden = photo_data.steps_hidden_photos.get(s.id, [])

        # Convert to PageLayout objects
        page_layouts = [PageLayout(photos=[p.id for p in p_page]) for p_page in pages]

        new_step_layout = StepLayout(
            step_id=s.id,
            name=s.display_name,  # User requested display name
            pages=page_layouts,
            hidden_photos=[h.id for h in hidden],
            cover_photo_id=cover.id if cover else None,
        )
        new_steps[s.id] = new_step_layout

    # Merge with existing overrides for steps NOT in target_steps (if partial regen)
    if step_id:
        # We only updated one step. Keep others from existing layout_overrides.
        new_steps.update({sid: sl for sid, sl in layout_overrides.steps.items() if sid != step_id})

    final_layout = AlbumLayout(steps=new_steps)

    try:
        # Write to disk
        layout_file.write_text(
            final_layout.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
        )
        logger.debug("Saved layout.json")
    except Exception:
        logger.exception("Failed to save layout.json")


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
    path_segments = _detect_segments(path_points) if path_points else []

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

    # Initialize photo_data object
    photo_data = AlbumPhotoData(
        steps_with_photos={},
        steps_cover_photos={},
        steps_photo_pages={},
    )

    # Initial Load
    # We populate photo_data in-place
    asyncio.run(_reload_step_data(None, steps, args.trip_dir, photo_data, args.out))

    use_step_range = args.progress_mode == "step-range"

    # Determine editor mode
    # If args.edit is True, we enable editor mode in config
    editor_mode = args.edit or False

    album_config = AlbumGenerationConfig(
        trip_data=trip_data,
        trip_display_data=trip_display,
        output_dir=args.out,
        editor_mode=editor_mode,
    )

    # Initial Generation
    html_path = asyncio.run(
        _generate_html_album(
            steps,
            photo_data,
            album_config,
            use_step_range=use_step_range,
            light_mode=args.light_mode,
        )
    )

    if editor_mode:
        logger.info("Starting Editor Mode...")

        async def regenerate_callback(step_id: int) -> None:
            logger.info("Regenerating step %s...", step_id)
            await _reload_step_data(step_id, steps, args.trip_dir, photo_data, args.out)
            # Re-generate HTML
            await _generate_html_album(
                steps,
                photo_data,
                album_config,
                use_step_range=use_step_range,
                light_mode=args.light_mode,
            )
            logger.info("Regeneration complete.")

        server = EditorServer(args.out, Path(args.trip_dir).resolve(), regenerate_callback)
        # Block until user quits
        server.run(port=8000)
    # Standard flow
    elif args.pdf:
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
