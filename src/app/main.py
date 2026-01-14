"""Main CLI application for generating photo albums."""

from __future__ import annotations

import asyncio
import os
import webbrowser
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from rich import get_console

from src.album.generator import generate_album_html
from src.app.edit import EditorServer
from src.core.cache import clear_cache
from src.core.dates import get_display_date_range
from src.core.logger import get_logger
from src.core.text import is_hebrew
from src.data.context import TripTemplateCtx
from src.data.layout import AlbumLayout, PageLayout, StepLayout
from src.data.locations import PathPoint, load_locations
from src.data.models import (
    AlbumPhoto,
    Step,
    Trip,
)
from src.data.trip import EnrichedStep
from src.media.processor import process_step_photos
from src.services.altitude import fetch_all_altitudes
from src.services.client import APIClient
from src.services.flags import fetch_flag
from src.services.maps import fetch_map
from src.services.weather import fetch_weather

from .args import Args

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.data.models import Step

logger = get_logger(__name__)


async def enrich_steps(steps: Sequence[Step]) -> Sequence[EnrichedStep]:
    """Fetch all external data concurrently."""
    async with APIClient() as client:
        results = await asyncio.gather(
            *(
                asyncio.gather(
                    fetch_weather(client, step),
                    fetch_flag(client, step.location.country_code),
                    fetch_map(client, step.location),
                )
                for step in steps
            ),
        )

        alts = await fetch_all_altitudes(client, steps)

    return [
        EnrichedStep(
            **step.model_dump(by_alias=True),  # pyright: ignore[reportAny]
            altitude=altitude,
            weather=weather,
            flag=flag,
            map=map_,
        )
        for step, altitude, (weather, flag, map_) in zip(steps, alts, results, strict=True)
    ]


def _generate_html_album(
    steps: Sequence[EnrichedStep],
    photo_data: AlbumPhoto,
    path_points: list[PathPoint],
    trip_template_ctx: TripTemplateCtx,
    output_dir: Path,
    *,
    edit: bool,
) -> Path:
    with get_console().status("[bold blue]Generating album HTML..."):
        html_path = generate_album_html(
            steps,
            photo_data,
            path_points,
            trip_template_ctx,
            output_dir,
            edit=edit,
        )
    logger.info("Generated: %s", html_path, extra={"success": True})
    return html_path


def _open_file(file_path: Path) -> None:
    wayland_display = os.environ.pop("WAYLAND_DISPLAY", None)
    webbrowser.open(f"file://{file_path.absolute()}")
    if wayland_display:
        os.environ["WAYLAND_DISPLAY"] = wayland_display


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
            page.pdf(
                path=str(pdf_path),
                format="A4",
                landscape=True,
                print_background=True,
            )
            browser.close()
        logger.info("PDF generated: %s", pdf_path, extra={"success": True})
    except ImportError:
        logger.warning("Playwright not installed. Install with: playwright install chromium")
        logger.info("Skipping PDF generation.")


def resolve_cover_photo_path(trip_data: Trip, args: Args) -> str | None:
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
    return trip_data.cover_photo.path


def _reload_step_data(
    step_id: int | None,
    all_steps: Sequence[Step],
    trip_dir: Path,
    photo_data: AlbumPhoto,
    output_dir: Path,
) -> None:
    """Reloads step data, applying any layout overrides from layout.json."""
    logger.info("Reloading layout data...")

    # Reload layout file - Always reload from disk to get latest editor changes
    layout_file = output_dir / "layout.json"
    layout_overrides = AlbumLayout(steps={})

    if layout_file.exists():
        layout_overrides = AlbumLayout.model_validate_json(layout_file.read_bytes())

    # Iterate all steps in layout_overrides to see what is claimed.
    global_used_ids = set[Path]()
    for s_layout in layout_overrides.steps.values():
        if s_layout.cover_photo:
            global_used_ids.add(s_layout.cover_photo)
        global_used_ids.update(s_layout.hidden_photos)
        for p in s_layout.pages:
            global_used_ids.update(p.photos)

    target_steps = [s for s in all_steps if s.id == step_id] if step_id else all_steps

    for step in target_steps:
        # Check for overrides
        step_layout = layout_overrides.steps.get(step.id)

        # Reprocess photos with overrides
        photos, cover_photo, photo_pages, hidden_photos = process_step_photos(
            step, trip_dir, global_used_ids, step_layout
        )

        # Update shared state
        photo_data.steps_with_photos[step.id] = photos
        photo_data.steps_cover_photos[step.id] = cover_photo
        photo_data.steps_photo_pages[step.id] = photo_pages
        photo_data.steps_hidden_photos[step.id] = hidden_photos

    # Rebuild layout object from processed results to include defaults and overrides
    new_steps: dict[int, StepLayout] = {}

    for step in target_steps:
        cover = photo_data.steps_cover_photos[step.id]
        pages = photo_data.steps_photo_pages.get(step.id, [])
        hidden = photo_data.steps_hidden_photos.get(step.id, [])

        # Convert to PageLayout objects
        page_layouts = [PageLayout(photos=[p.path for p in p_page]) for p_page in pages]

        new_steps[step.id] = StepLayout(
            id=step.id,
            name=step.name,
            pages=page_layouts,
            hidden_photos=hidden,
            cover_photo=cover,
        )

    # Merge with existing overrides for steps NOT in target_steps (if partial regen)
    if step_id:
        # We only updated one step. Keep others from existing layout_overrides.
        new_steps.update({sid: sl for sid, sl in layout_overrides.steps.items() if sid != step_id})

    final_layout = AlbumLayout(steps=new_steps)

    layout_file.write_text(
        final_layout.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )


def main() -> None:
    args = Args(underscores_to_dashes=True).parse_args()

    trip_json_path = args.trip_dir / "trip.json"
    if not trip_json_path.exists():
        logger.error(
            "trip.json not found at %s. Please ensure the trip directory contains trip.json",
            trip_json_path,
        )
        return

    logger.info("Found trip.json at %s", trip_json_path)

    if args.no_cache:
        clear_cache()
        logger.warning("Cleared cache")

    with get_console().status("[bold blue]Loading trip data..."):
        trip = Trip.model_validate_json(
            trip_json_path.read_text(encoding="utf-8"),
        )

    steps = asyncio.run(enrich_steps(args.filter_steps(trip.all_steps)))

    display_title = args.title or trip.name
    display_subtitle = args.subtitle or trip.summary

    min_time = steps[0].date.timestamp()
    max_time = (steps[-1].date + timedelta(days=1)).timestamp()
    path_points, path_segments = load_locations(args.trip_dir, min_time, max_time)

    trip_template_ctx = TripTemplateCtx(
        title=display_title,
        title_dir="rtl" if is_hebrew(display_title) else "ltr",
        date_range=get_display_date_range(steps),
        subtitle=display_subtitle,
        subtitle_dir="rtl" if is_hebrew(display_subtitle) else "ltr",
        cover_photo=(resolve_cover_photo_path(trip, args)),
        path_points=path_points,
        path_segments=path_segments,
    )

    args.out.mkdir(parents=True, exist_ok=True)

    # Initialize photo_data object
    photo_data = AlbumPhoto(
        steps_with_photos={},
        steps_cover_photos={},
        steps_photo_pages={},
    )

    _reload_step_data(None, steps, args.trip_dir, photo_data, args.out)

    # Initial Generation
    html_path = _generate_html_album(
        steps,
        photo_data,
        path_points,
        trip_template_ctx,
        args.out,
        edit=args.edit,
    )

    if args.edit:
        logger.info("Starting Editor Mode...")

        def regenerate_callback(step_id: int) -> None:
            logger.info("Regenerating step %s...", step_id)
            _reload_step_data(step_id, steps, args.trip_dir, photo_data, args.out)
            _generate_html_album(
                steps,
                photo_data,
                path_points,
                trip_template_ctx,
                args.out,
                edit=args.edit,
            )
            logger.info("Regeneration complete.")

        EditorServer(args.out, args.trip_dir, regenerate_callback).run()

    elif args.pdf:
        pdf_path = args.out / "album.pdf"
        with get_console().status("[bold blue]Generating PDF..."):
            _generate_pdf(html_path, pdf_path)
        logger.info("Generated: %s", pdf_path, extra={"success": True})
        if not args.no_open:
            _open_file(pdf_path)
    else:
        logger.info("Album generated successfully!", extra={"success": True})
        if not args.no_open:
            _open_file(html_path)
