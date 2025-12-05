"""CLI argument parsing for the album generator."""

from pathlib import Path
from typing import Literal

from tap import Tap


class Args(Tap):
    trip_dir: Path  # Directory containing unzipped Polarsteps data
    steps: slice | None = None  # Step range to include, e.g. "99-110" or "99". 0-indexed
    sample: int | None = None  # Sample N evenly distributed steps (for testing across countries)
    title: str | None = None  # Override trip title
    cover_photo: Path | None = None  # Override cover photo path
    out: Path = Path("output")  # Output directory for HTML/PDF files
    pdf: bool = False  # Generate PDF file using Playwright (requires playwright install)
    progress_mode: Literal["original", "step-range"] = "step-range"
    """Progress bar mode: 'original' uses trip days, 'step-range' uses step range"""
    light_mode: bool = False  # Use light mode instead of dark mode
    no_open: bool = False  # Do not automatically open the generated album in the browser
    no_cache: bool = False  # Force regeneration of cached data (maps, weather, etc.)

    def configure(self) -> None:
        self.add_argument("trip_dir", type=Path)
        self.add_argument("--steps", type=_step_slice)


def _step_slice(range_str: str) -> slice:
    if not range_str.strip():
        raise ValueError("--steps argument cannot be empty")

    if "-" in range_str:
        start, end = range_str.split("-", 1)
        return slice(int(start.strip()), int(end.strip()) + 1)

    step_num = int(range_str.strip())
    return slice(step_num, step_num + 1)
