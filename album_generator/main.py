"""Main CLI application for generating photo albums."""

import argparse
from pathlib import Path
from typing import Tuple
import sys

from .data_loader import load_trip_data, get_step_photo_dir, get_steps_in_range
from .image_selector import select_step_image
from .html_generator import generate_album_html


def parse_step_range(range_str: str) -> Tuple[int, int]:
    """Parse step range string like '99-110' or '99'."""
    if "-" in range_str:
        start, end = range_str.split("-", 1)
        return int(start.strip()), int(end.strip())
    else:
        step_num = int(range_str.strip())
        return step_num, step_num


def generate_pdf(html_path: Path, pdf_path: Path):
    """Generate PDF from HTML using Playwright."""
    try:
        from playwright.sync_api import sync_playwright

        print(f"Generating PDF from HTML...")
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
        print(f"PDF generated: {pdf_path}")
    except ImportError:
        print(
            "Warning: Playwright not installed. Install with: playwright install chromium"
        )
        print("Skipping PDF generation.")
    except Exception as e:
        print(f"Warning: Failed to generate PDF: {e}")
        print(
            "You can still open the HTML file in your browser and print to PDF manually."
        )


def main():
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
        print(f"Error: trip.json not found at {trip_json}", file=sys.stderr)
        sys.exit(1)

    # Get font path (internal to package)
    font_path = Path(__file__).parent / "static" / "Renner.ttf"
    if not font_path.exists():
        print(f"Error: Font file not found at {font_path}", file=sys.stderr)
        sys.exit(1)

    # Load trip data
    print(f"Loading trip data from {trip_json}...")
    trip_data = load_trip_data(trip_json)
    all_steps = trip_data.all_steps

    if not all_steps:
        print("Error: No steps found in trip data", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(all_steps)} total steps")

    # Filter steps by range
    if args.steps:
        start, end = parse_step_range(args.steps)
        steps = get_steps_in_range(all_steps, start, end)
        print(f"Filtered to steps {start}-{end}: {len(steps)} steps")
    else:
        steps = all_steps
        print(f"Using all {len(steps)} steps")

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    # Collect images for each step
    step_images = {}
    for step in steps:
        print(f"Processing step: {step.city}...")

        # Get photo directory
        photo_dir = get_step_photo_dir(args.trip_dir, step)
        if not photo_dir:
            print(f"  Warning: No photo directory found")
            step_images[step.id] = None
        else:
            # Select image
            image_path = select_step_image(photo_dir)
            if image_path:
                print(f"  Selected image: {image_path.name}")
                step_images[step.id] = image_path
            else:
                print(f"  Warning: No suitable image found")
                step_images[step.id] = None

    # Generate single HTML file with all steps
    html_path = args.output / "album.html"
    use_step_range = args.progress_mode == "step-range"
    print(f"\nGenerating album HTML...")
    generate_album_html(
        steps,
        step_images,
        trip_data,
        font_path,
        html_path,
        use_step_range,
        args.light_mode,
    )
    print(f"Generated: {html_path}")

    # Generate PDF if requested
    if args.pdf:
        pdf_path = args.output / "album.pdf"
        generate_pdf(html_path, pdf_path)
    else:
        print(f"\nAlbum generated successfully!")
        print(f"Open {html_path} in your browser to view the album.")
        print(f"Use --pdf flag to generate a PDF file automatically.")


if __name__ == "__main__":
    main()
