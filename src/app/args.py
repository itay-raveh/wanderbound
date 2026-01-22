"""CLI argument parsing for the album generator."""

# pyright: reportUninitializedInstanceVariable=false, reportAny=false, reportExplicitAny=false
from __future__ import annotations

import re
from pathlib import Path
from termios import VLNEXT
from typing import TYPE_CHECKING, Any, Self, override

from tap import Tap

if TYPE_CHECKING:
    from _typeshed import StrPath, Unused


class ExistingPath(Path):
    """Path that must exist."""

    def __init__(self, *args: StrPath, **kwargs: Unused) -> None:
        super().__init__(*args)
        if not self.exists():
            raise ValueError(f"Path does not exist: {self}")


class File(ExistingPath):
    """Path that must be a file."""

    def __init__(self, *args: StrPath, **kwargs: Unused) -> None:
        super().__init__(*args)
        if not self.is_file():
            raise ValueError(f"Path is not a file: {self}")


class Folder(ExistingPath):
    """Path that must be a directory."""

    def __init__(self, *args: StrPath, **kwargs: Unused) -> None:
        super().__init__(*args)
        if not self.is_dir():
            raise ValueError(f"Path is not a directory: {self}")


class SliceList(list[slice]):
    def __init__(self, value: str | list[slice[int]] | None = None) -> None:
        super().__init__()

        if not value:
            return

        if isinstance(value, list):
            self.extend(value)
            return

        for part in value.split(","):
            if re.match(r"^\d+-\d+$", part):
                start, end = part.split("-")
                new = slice(int(start.strip()), int(end.strip()) + 1)
            elif re.match(r"^\d+$", part):
                val = int(part.strip())
                new = slice(val, val + 1)
            else:
                raise ValueError(f"{part} is not a valid range")

            if 1 <= new.start < new.stop:
                self.append(new)
            else:
                raise ValueError(f"{part} is not a valid range")

    def __repr__(self) -> str:
        return ",".join(f"{slc.start}-{slc.stop - 1}" for slc in self)


class Args(Tap):
    trip: Folder  # Folder containing Polarsteps trip data (`trip.json` etc.)
    output: Folder  # Output folder
    steps: SliceList | None = None  # Step range to include, e.g. "15,99-110"
    maps: SliceList | None = None  # Ranges of steps for which to add a map
    title: str | None = None  # Override trip title
    subtitle: str | None = None  # Override trip subtitle ("summary" field in trip.json)
    cover: File | None = None  # Override trip cover photo
    back_cover: File | None = None  # Add back cover photo (default: same as the front)
    no_cache: bool = False  # Force regeneration of cached data (maps, weather, etc.)

    @override
    def process_args(self) -> None:
        self._reindex_maps_slices()

    def _reindex_maps_slices(self) -> None:
        if not self.steps or not self.maps:
            return

        # Build mapping from Original Index -> Filtered Index
        idx_map: dict[int, int] = {}
        current_idx = 0
        for slc in self.steps:
            for orig_idx in range(slc.start, slc.stop):
                idx_map[orig_idx] = current_idx
                current_idx += 1

        maps_slices = SliceList()
        for map_slice in self.maps:
            if map_slice.start not in idx_map:
                raise ValueError(f"Map start index {map_slice.start} is not in the included steps!")

            # slice.stop is exclusive
            last_included_orig = map_slice.stop - 1
            if last_included_orig not in idx_map:
                raise ValueError(
                    f"Map end index {last_included_orig} is not in the included steps!"
                )

            maps_slices.append(slice(idx_map[map_slice.start], idx_map[last_included_orig] + 1))

        self.maps = maps_slices
