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
    maps: str | None = None  # Ranges of steps for which to add a map, e.g. "10-15,30-40"
    title: str | None = None  # Override trip title
    subtitle: str | None = None  # Override trip subtitle ("summary" field in trip.json)
    cover: Path | None = None  # Override trip cover photo
    back_cover: Path | None = None  # Add back cover photo (default: same as the front)
    no_cache: bool = False  # Force regeneration of cached data (maps, weather, etc.)

    @property
    def maps_slices(self) -> list[slice[int]] | None:
        if self.maps:
            return _parse_map_ranges(self.maps)
        return None

    @property
    def steps_slice(self) -> slice[int] | None:
        if self.steps:
            return _step_slice(self.steps)
        return None

    def filter_steps(self, all_steps: Sequence[Step]) -> Sequence[Step]:
        if self.steps:
            logger.info("Filtered to steps %s", self.steps)
            return all_steps[_step_slice(self.steps)]

        logger.info("Using all %d steps", len(all_steps))
        return all_steps


def _step_slice(range_str: str) -> slice:
    if "-" in range_str:
        start, end = range_str.split("-", 1)
        return slice(int(start.strip()), int(end.strip()) + 1)

    step = int(range_str.strip())
    return slice(step, step + 1)


def _parse_map_ranges(range_str: str) -> list[slice]:
    ranges: list[slice] = []
    for part in range_str.split(","):
        if "-" in part:
            start, end = part.split("-", 1)
            ranges.append(slice(int(start.strip()), int(end.strip()) + 1))
        else:
            val = int(part.strip())
            ranges.append(slice(val, val + 1))
    return ranges
