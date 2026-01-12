"""CLI argument parsing for the album generator."""
# pyright: basic

from pathlib import Path
from typing import Literal

from tap import Tap

from src.core.logger import get_logger
from src.data.trip import Step

logger = get_logger(__name__)


class Args(Tap):
    trip_dir: Path  # Directory containing unzipped Polarsteps data
    steps: slice[int] | None = None  # Step range to include, e.g. "99-110" or "99". 0-indexed
    sample: int | None = None  # Sample N evenly distributed steps (for testing across countries)
    title: str | None = None  # Override trip title
    subtitle: str | None = None  # Override trip subtitle ("summary" field in trip.json)
    cover_photo: Path | None = None  # Override cover photo path
    out: Path = Path("output")  # Output directory for HTML/PDF files
    pdf: bool = False  # Generate PDF file using Playwright (requires playwright install)
    progress_mode: Literal["original", "step-range"] = "step-range"
    """Progress bar mode: 'original' uses trip days, 'step-range' uses step range"""
    light_mode: bool = False  # Use light mode instead of dark mode
    no_open: bool = False  # Do not automatically open the generated album in the browser
    no_cache: bool = False  # Force regeneration of cached data (maps, weather, etc.)
    edit: bool = False  # Enable manual layout editor

    def configure(self) -> None:
        self.add_argument("trip_dir", type=Path)
        self.add_argument("--steps", type=_step_slice)

    def filter_steps(self, all_steps: list[Step]) -> list[Step]:
        logger.info("Found %d total steps", len(all_steps))

        if self.sample:
            dist_steps = _get_steps_distributed(all_steps, self.sample)
            logger.info("Sampled %d steps evenly across the trip", len(dist_steps))
            return dist_steps

        if self.steps:
            range_steps: list[Step] = all_steps[self.steps]
            logger.info(
                "Filtered to steps %d-%d: %d steps",
                self.steps.start,
                self.steps.stop,
                len(range_steps),
            )
            return range_steps

        logger.info("Using all %d steps", len(all_steps))
        return all_steps


def _step_slice(range_str: str) -> slice:
    if not range_str.strip():
        raise ValueError("'--steps' flag cannot be empty")

    if "-" in range_str:
        start, end = range_str.split("-", 1)
        return slice(int(start.strip()), int(end.strip()) + 1)

    step_num = int(range_str.strip())
    return slice(step_num, step_num + 1)


def _get_steps_distributed(all_steps: list[Step], count: int) -> list[Step]:
    if count == 1:
        return [all_steps[len(all_steps) // 2]]

    step_indices = [(i * (len(all_steps) - 1) // (count - 1)) for i in range(count)]

    return [all_steps[idx] for idx in dict.fromkeys(step_indices)]
