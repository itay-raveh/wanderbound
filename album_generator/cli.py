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


def parse_step_range(range_str: str) -> tuple[int, int]:
    """Parse step range string into start and end step numbers.

    Args:
        range_str: Step range string in format "start-end" or single step number.
            Must be a non-empty string.

    Returns:
        Tuple of (start, end) step numbers (1-indexed, inclusive).
        If single number provided, both start and end are the same.

    Raises:
        TypeError: If range_str is not a string.
        ValueError: If range_str cannot be parsed as integers.

    Examples:
        >>> parse_step_range("99-110")
        (99, 110)
        >>> parse_step_range("99")
        (99, 99)
    """
    if not isinstance(range_str, str):
        raise TypeError(f"range_str must be a string, got {type(range_str).__name__}")
    if not range_str.strip():
        raise ValueError("range_str cannot be empty")

    if "-" in range_str:
        start, end = range_str.split("-", 1)
        return int(start.strip()), int(end.strip())
    else:
        step_num = int(range_str.strip())
        return step_num, step_num


__all__ = ["parse_args"]
