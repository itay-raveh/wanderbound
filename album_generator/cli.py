"""CLI argument parsing for the album generator."""

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command line arguments for the album generator.

    Returns:
        argparse.Namespace: Parsed arguments containing:
            - trip_dir: Path to trip directory (default: "trip")
            - steps: Step range string (e.g., "99-110" or "99")
            - sample: Number of evenly distributed steps to sample
            - output: Output directory path (default: "output")
            - pdf: Whether to generate PDF
            - progress_mode: Progress bar mode ("original" or "step-range")
            - light_mode: Whether to use light mode
            - clear_photos_cache: Whether to clear cached photo configuration
    """
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
    parser.add_argument(
        "--clear-photos-cache",
        action="store_true",
        help="Clear cached photo layout configuration and regenerate from scratch",
    )

    return parser.parse_args()


__all__ = ["parse_args"]
