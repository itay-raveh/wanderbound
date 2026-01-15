"""CLI argument parsing for the album generator."""

# pyright: reportUninitializedInstanceVariable=false
from collections.abc import Sequence
from pathlib import Path

from tap import Tap

from src.core.logger import get_logger
from src.data.trip import Step

logger = get_logger(__name__)


class Args(Tap):
    trip: Path  # Directory containing Polarsteps data (`trip.json` etc.)
    output: Path = Path("output")  # Output directory
    steps: str | None = None  # Step range to include, e.g. "99-110" or "99". 0-indexed
    title: str | None = None  # Override trip title
    subtitle: str | None = None  # Override trip subtitle ("summary" field in trip.json)
    cover: Path | None = None  # Override trip cover photo
    back_cover: Path | None = None  # Add back cover photo (default: same as the front)
    no_cache: bool = False  # Force regeneration of cached data (maps, weather, etc.)

    def filter_steps(self, all_steps: Sequence[Step]) -> Sequence[Step]:
        if self.steps:
            logger.info("Filtered to steps %s", self.steps)
            return all_steps[_step_slice(self.steps)]

        logger.info("Using all %d steps", len(all_steps))
        return all_steps


def _step_slice(range_str: str) -> slice:
    if not range_str.strip():
        raise ValueError("'--steps' flag cannot be empty")

    if "-" in range_str:
        start, end = range_str.split("-", 1)
        return slice(int(start.strip()), int(end.strip()) + 1)

    step = int(range_str.strip())
    return slice(step, step + 1)
