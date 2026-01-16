from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class Photo(BaseModel):
    path: Path
    width: int
    height: int

    def __hash__(self) -> int:
        return hash(self.path)

    @property
    def is_portrait(self) -> float:
        return self.width / self.height < 4 / 5

    @property
    def is_video(self) -> bool:
        return False


class Video(Photo):
    video_src: Path
    video_timestamp: float

    @property
    def is_video(self) -> bool:
        return True


SpecialLayoutClass = Literal["three-portraits", "one-portrait-two-landscapes"]


class PageLayout(BaseModel):
    # Note: Video must come before Photo for Pydantic to match the subclass fields first
    photos: list[Video | Photo]
    layout_class: SpecialLayoutClass | None = None


class StepLayout(BaseModel):
    id: int
    name: str
    cover: Path
    pages: list[PageLayout]
    hidden_photos: list[Path]


class AlbumLayout(BaseModel):
    steps: dict[int, StepLayout]
