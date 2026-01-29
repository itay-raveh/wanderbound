from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    DirectoryPath,
    Field,
    FilePath,
    PlainSerializer,
    model_validator,
)


def _parse_slice_string(part: str) -> slice[int]:
    if "-" in part:
        start_str, *others, end_str = part.split("-")

        if others:
            raise ValueError(f"'{part}' is invalid. Expected 'start-end' (e.g., '1-5').")

        if not start_str.isdigit() or not end_str.isdigit():
            raise ValueError(f"'{part}' is invalid. Expected 'start-end' (e.g., '1-5').")

        start, end = int(start_str), int(end_str)

        if start >= end:
            raise ValueError(f"'{part}' is invalid: Start ({start}) must be < End ({end}).")

        return slice(start, end + 1)

    if not part.isdigit():
        raise ValueError(f"'{part}' is invalid. Expected number (e.g., '1').")

    idx = int(part)
    return slice(idx, idx + 1)


def _parse_slices_string(v: str | list[slice[int]]) -> list[slice[int]]:
    if isinstance(v, list):
        return v

    parts = [p.strip() for p in v.strip().split(",") if p.strip()]

    if not parts:
        raise ValueError("Invalid")

    return list(map(_parse_slice_string, parts))


def str_slices(v: list[slice[int]]) -> str:
    parts: list[str] = []
    for s in v:
        if s.stop - s.start > 1:
            parts.append(f"{s.start}-{s.stop - 1}")
        else:
            parts.append(f"{s.start}")
    return ",".join(parts)


if TYPE_CHECKING:
    SliceList = list[slice[int]]
else:
    SliceList = Annotated[
        list[slice],
        BeforeValidator(_parse_slices_string),
        PlainSerializer(str_slices, return_type=str),
    ]


class GeneratorArgs(BaseModel):
    trip: DirectoryPath = Field(description="Folder containing Polarsteps trip data")
    output: DirectoryPath = Field(description="Output folder")
    title: str | None = Field(default=None, description="Override trip title")
    subtitle: str | None = Field(default=None, description="Override trip subtitle")
    cover: FilePath | None = Field(default=None, description="Override trip cover photo")
    back_cover: FilePath | None = Field(
        default=None, description="Add back cover photo (default: same as front)"
    )
    steps: SliceList | None = Field(
        default=None, description="Step range to include (e.g. '1-5, 8')"
    )
    maps: SliceList | None = Field(
        default=None, description="Ranges of steps for which to add a map"
    )
    no_cache: bool = Field(default=False, description="Force regeneration of cached data")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def after(self) -> GeneratorArgs:
        self._reindex_maps_slices()
        return self

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

        maps_slices: list[slice] = []
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
