from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class CoverPhoto(BaseModel):
    uuid: str | None = None
    path: str | None = None


@dataclass(unsafe_hash=True)
class PhotoWithDims:
    path: Path
    width: int
    height: int

    @property
    def aspect_ratio(self) -> float:
        return float(self.width) / float(self.height)


PageLayout = Literal["three-portraits", "portrait-landscape-split"]


@dataclass
class PhotoPage:
    photos: list[Path]
    layout_class: PageLayout | None = None
    grid_style: str | None = None


@dataclass
class AlbumPhoto:
    steps_with_photos: dict[int, list[PhotoWithDims]]
    steps_cover_photos: dict[int, Path]
    steps_photo_pages: dict[int, list[list[PhotoWithDims]]]
    steps_hidden_photos: dict[int, list[Path]] = field(default_factory=dict)
