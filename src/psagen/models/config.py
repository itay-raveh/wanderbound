from pathlib import Path
from typing import Self

from pydantic import (
    BaseModel,
    Field,
    RootModel,
    model_serializer,
    model_validator,
)

from psagen.models.layout import StepLayout
from psagen.models.trip import Location, TripHeader


class Slice(BaseModel):
    start: int
    end: int

    @model_validator(mode="before")
    @classmethod
    def parse(cls, v: str | Self) -> dict[str, int] | Self:
        if not isinstance(v, str):
            return v

        part = v.strip()

        if "-" in part:
            start_str, *others, end_str = part.split("-")

            if others:
                raise ValueError(f"'{part}' is invalid")

            if not start_str.isdigit() or not end_str.isdigit():
                raise ValueError(f"'{part}' is invalid")

            start, end = int(start_str), int(end_str)

            if start >= end:
                raise ValueError(f"'{part}' is invalid: Start ({start}) must be < End ({end}).")

            return {"start": start, "end": end}

        if not part.isdigit():
            raise ValueError(f"'{part}' is invalid.")

        idx = int(part)
        return {"start": idx, "end": idx}

    def __str__(self) -> str:
        if self.start == self.end:
            return str(self.start)
        return f"{self.start}-{self.end}"

    @model_serializer
    def serialize(self) -> str:
        return str(self)

    def as_slice(self) -> slice:
        return slice(self.start, self.end + 1)


class SliceList(RootModel[list[Slice]]):
    root: list[Slice]

    @model_validator(mode="before")
    @classmethod
    def parse_list(cls, v: str | Self) -> list[str] | Self:
        if not isinstance(v, str):
            return v

        if not v.strip():
            return []

        return [s.strip() for s in v.split(",") if s.strip()]

    def __str__(self) -> str:
        return ", ".join(str(s) for s in self.root)

    @model_serializer
    def serialize(self) -> str:
        return str(self)


class AlbumSettings(BaseModel, validate_assignment=True):
    steps_ranges: SliceList = Field(examples=["1-5, 8"])
    title: str
    subtitle: str | None = None
    front_cover_photo: str
    back_cover_photo: str
    maps_ranges: SliceList = Field(
        default_factory=lambda: SliceList([]),
        description="Ranges of steps for which to add additional maps",
        examples=["1-5, 8"],
    )
    home: Location | None = Field(default=None, description="To show furthest step from home")


class AlbumConfig(BaseModel):
    trip_name: str
    settings: AlbumSettings
    layouts: dict[int, StepLayout]

    @classmethod
    def from_trip_folder(cls, trip_folder: Path) -> Self:
        config_json = trip_folder / "config.json"

        if config_json.exists():
            return cls.model_validate_json(config_json.read_bytes())

        trip_json = trip_folder / "trip.json"
        trip = TripHeader.model_validate_json(trip_json.read_bytes())

        return cls(
            trip_name=trip.name,
            layouts={},
            settings=AlbumSettings(
                steps_ranges=SliceList([Slice(start=0, end=trip.step_count - 1)]),
                title=trip.title,
                subtitle=trip.subtitle,
                front_cover_photo=trip.cover_photo.path,
                back_cover_photo=trip.cover_photo.path,
            ),
        )

    def persist_in_trip_folder(self, trip_folder: Path) -> None:
        (trip_folder / "config.json").write_text(self.model_dump_json(indent=2))
