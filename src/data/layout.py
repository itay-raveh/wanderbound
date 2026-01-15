from pathlib import Path
from typing import Literal

from pydantic import BaseModel


# noinspection PyDataclass
class Photo(BaseModel, frozen=True):
    path: Path
    width: int
    height: int

    @property
    def is_portrait(self) -> float:
        return self.width / self.height < 4 / 5


SpecialLayoutClass = Literal["three-portraits", "one-portrait-two-landscapes"]


class PageLayout(BaseModel):
    photos: list[Photo]
    layout_class: SpecialLayoutClass | None = None


class StepLayout(BaseModel):
    id: int
    name: str
    cover: Path
    pages: list[PageLayout]
    hidden_photos: list[Path]


class AlbumLayout(BaseModel):
    steps: dict[int, StepLayout]
