"""CLI argument parsing for the album generator."""

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate HTML photo album from Polarsteps trip data"
    )
    parser.add_argument(
        "--trip-dir",
        type=Path,
        default=Path("trip"),
        help="Directory containing trip.json and step folders (default: trip)",
    )
    parser.add_argument("--steps", type=str, help='Step range to include (e.g., "99-110" or "99")')
    parser.add_argument(
        "--sample",
        type=int,
        help=(
            "Sample N evenly distributed steps across the entire trip "
            "(useful for testing across countries)"
        ),
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
        help=(
            "Progress bar mode: 'original' uses trip days, "
            "'step-range' uses step range (default: step-range)"
        ),
    )
    parser.add_argument(
        "--light-mode",
        action="store_true",
        help="Use light mode instead of dark mode (default: dark mode)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not automatically open the generated album in the browser",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Force regeneration of cached data (maps, weather, etc.)",
    )

    return parser.parse_args()


def parse_step_range(range_str: str) -> tuple[int, int]:
    if not range_str.strip():
        raise ValueError("range_str cannot be empty")

    if "-" in range_str:
        start, end = range_str.split("-", 1)
        return int(start.strip()), int(end.strip())
    step_num = int(range_str.strip())
    return step_num, step_num


__all__ = ["parse_args"]
