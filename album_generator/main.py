"""Main CLI application for generating photo albums."""

import argparse
import sys
import webbrowser
from pathlib import Path

from .data_loader import (
    get_step_photo_dir,
    get_steps_distributed,
    get_steps_in_range,
    load_trip_data,
)
from .html_generator import generate_album_html
from .image_selector import select_step_image
from .logger import create_progress, get_console, get_logger

logger = get_logger(__name__)
console = get_console()


def parse_step_range(range_str: str) -> tuple[int, int]:
    """Parse step range string like '99-110' or '99'."""
    if "-" in range_str:
        start, end = range_str.split("-", 1)
        return int(start.strip()), int(end.strip())
    else:
        step_num = int(range_str.strip())
        return step_num, step_num


def generate_pdf(html_path: Path, pdf_path: Path) -> None:
    """Generate PDF from HTML using Playwright."""
    try:
        from playwright.sync_api import sync_playwright

        logger.info("Generating PDF from HTML...")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file://{html_path.absolute()}")
            page.wait_for_load_state("networkidle")
            page.set_viewport_size({"width": 1123, "height": 794})

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
        logger.warning(
            "Playwright not installed. Install with: playwright install chromium"
        )
        logger.info("Skipping PDF generation.")
    except Exception as e:
        logger.error(f"Failed to generate PDF: {e}", exc_info=True)
        logger.info(
            "You can still open the HTML file in your browser and print to PDF manually."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate HTML photo album from Polarsteps trip data"
    )
    parser.add_argument(
        "--trip-dir",
        type=Path,
        default=Path("trip"),
        help="Directory containing trip.json and step folders (default: trip)",
    )
    parser.add_argument(
        "--steps", type=str, help='Step range to include (e.g., "99-110" or "99")'
    )
    parser.add_argument(
        "--sample",
        type=int,
        help="Sample N evenly distributed steps across the entire trip (useful for testing across countries)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Output directory for HTML/PDF files (default: output)",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Generate PDF file using Playwright (requires playwright install)",
    )
    parser.add_argument(
        "--progress-mode",
        choices=["original", "step-range"],
        default="step-range",
        help="Progress bar mode: 'original' uses trip days, 'step-range' uses step range (default: step-range)",
    )
    parser.add_argument(
        "--light-mode",
        action="store_true",
        help="Use light mode instead of dark mode (default: dark mode)",
    )

    args = parser.parse_args()

    # Validate inputs
    trip_json = args.trip_dir / "trip.json"
    if not trip_json.exists():
        logger.error(f"trip.json not found at {trip_json}")
        sys.exit(1)

    # Get font path (internal to package)
    font_path = Path(__file__).parent / "static" / "Renner.ttf"
    if not font_path.exists():
        logger.error(f"Font file not found at {font_path}")
        sys.exit(1)

    # Load trip data
    with console.status("[bold blue]Loading trip data..."):
        logger.debug(f"Loading trip data from {trip_json}")
        trip_data = load_trip_data(trip_json)
        logger.debug("Trip data loaded successfully")
    all_steps = trip_data.all_steps

    if not all_steps:
        logger.error("No steps found in trip data")
        sys.exit(1)

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

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Output directory: {args.output}")

    # Collect images for each step
    step_images: dict[int, Path | None] = {}
    progress = create_progress("Processing steps")

    with progress:
        task_id = progress.add_task("Processing steps", total=len(steps))
        for step in progress.track(steps, task_id=task_id):
            logger.debug(f"Processing step: {step.city}")
            progress.update(task_id, description=f"Processing steps: {step.city}")

            # Get photo directory
            photo_dir = get_step_photo_dir(args.trip_dir, step)
            if not photo_dir:
                logger.warning(f"No photo directory found for step {step.city}")
                step_images[step.id] = None
            else:
                # Select image
                image_path = select_step_image(photo_dir)
                if image_path:
                    logger.debug(f"Selected image: {image_path.name}")
                    step_images[step.id] = image_path
                else:
                    logger.warning(f"No suitable image found for step {step.city}")
                    step_images[step.id] = None

        progress.update(task_id, description="Processing steps")

    # Generate single HTML file with all steps
    html_path = args.output / "album.html"
    use_step_range = args.progress_mode == "step-range"
    with console.status("[bold blue]Generating album HTML..."):
        logger.debug("Generating album HTML...")
        generate_album_html(
            steps,
            step_images,
            trip_data,
            font_path,
            html_path,
            use_step_range,
            args.light_mode,
        )
    logger.info(f"Generated: {html_path}", extra={"success": True})

    # Generate PDF if requested
    if args.pdf:
        pdf_path = args.output / "album.pdf"
        with console.status("[bold blue]Generating PDF..."):
            generate_pdf(html_path, pdf_path)
        logger.info(f"Generated: {pdf_path}", extra={"success": True})
        # Open PDF with default application
        try:
            webbrowser.open(f"file://{pdf_path.absolute()}")
            logger.info("Opened PDF in default application", extra={"success": True})
        except Exception as e:
            logger.warning(f"Failed to open PDF: {e}")
    else:
        logger.info("Album generated successfully!", extra={"success": True})
        # Open HTML in default browser
        try:
            webbrowser.open(f"file://{html_path.absolute()}")
            logger.info("Opened HTML in default browser", extra={"success": True})
        except Exception as e:
            logger.warning(f"Failed to open HTML: {e}")


if __name__ == "__main__":
    main()
