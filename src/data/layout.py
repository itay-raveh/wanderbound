from pathlib import Path

from pydantic import BaseModel


class PageLayout(BaseModel):
    photos: list[Path]


class StepLayout(BaseModel):
    step_id: int
    name: str
    cover_photo: Path
    pages: list[PageLayout]
    hidden_photos: list[Path] = []


class AlbumLayout(BaseModel):
    steps: dict[int, StepLayout]
