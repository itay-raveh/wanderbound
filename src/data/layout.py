from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class Photo(BaseModel):
    path: Path
    width: int
    height: int

    @property
    def aspect_ratio(self) -> float:
        return float(self.width) / float(self.height)


SpecialLayoutClass = Literal["three-portraits", "one-portrait-two-landscapes"]


class PageLayout(BaseModel):
    photos: list[Photo]
    layout_class: SpecialLayoutClass | None = None
    grid_style: str | None = None


class StepLayout(BaseModel):
    id: int
    name: str
    cover: Path
    pages: list[PageLayout]
    hidden_photos: list[Path]


class AlbumLayout(BaseModel):
    steps: dict[int, StepLayout]
