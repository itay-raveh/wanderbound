"""CLI argument parsing for the album generator."""

# pyright: reportUninitializedInstanceVariable=false
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from tap import Tap

from src.core.logger import get_logger

if TYPE_CHECKING:
    from src.data.trip import Step

logger = get_logger(__name__)


class Args(Tap):
    trip: Path  # Directory containing Polarsteps data (`trip.json` etc.)
    output: Path = Path("output")  # Output directory
    steps: str | None = None  # Step range to include, e.g. "15,99-110"
    maps: str | None = None  # Ranges of steps for which to add a map
    title: str | None = None  # Override trip title
    subtitle: str | None = None  # Override trip subtitle ("summary" field in trip.json)
    cover: Path | None = None  # Override trip cover photo
    back_cover: Path | None = None  # Add back cover photo (default: same as the front)
    no_cache: bool = False  # Force regeneration of cached data (maps, weather, etc.)

    @property
    def steps_slices(self) -> list[slice[int]] | None:
        if self.steps:
            return _parse_slices(self.steps)
        return None

    @property
    def maps_slices(self) -> list[slice[int]] | None:
        if self.maps:
            return _parse_slices(self.maps)
        return None

    def filter_steps(self, all_steps: list[Step]) -> list[Step]:
        if self.steps_slices:
            logger.info("Filtered to steps %s", self.steps)
            return sum((all_steps[slc] for slc in self.steps_slices), start=[])

        logger.info("Using all %d steps", len(all_steps))
        return all_steps

    def filter_map_slices(self, target_steps: list[Step]) -> list[slice[int]] | None:
        if not self.steps_slices:
            # All steps are included 1:1
            idx_map = {i: i for i in range(len(target_steps))}
        # Build mapping from Original Index -> Filtered Index
        else:
            idx_map: dict[int, int] = {}
            current_idx = 0
            for slc in self.steps_slices:
                for orig_idx in range(slc.start, slc.stop):
                    idx_map[orig_idx] = current_idx
                    current_idx += 1

        maps_slices: list[slice] = []
        for map_slice in self.maps_slices or []:
            if map_slice.start not in idx_map:
                logger.error("Map start index %d is not in the included steps!", map_slice.start)
                return None

            # slice.stop is exclusive
            last_included_orig = map_slice.stop - 1
            if last_included_orig not in idx_map:
                logger.error("Map end index %d is not in the included steps!", last_included_orig)
                return None

            maps_slices.append(slice(idx_map[map_slice.start], idx_map[last_included_orig] + 1))

        return maps_slices


def _parse_slices(range_str: str) -> list[slice[int]]:
    ranges: list[slice[int]] = []
    for part in range_str.split(","):
        if "-" in part:
            start, end = part.split("-", 1)
            ranges.append(slice(int(start.strip()), int(end.strip()) + 1))
        else:
            val = int(part.strip())
            ranges.append(slice(val, val + 1))
    return ranges
