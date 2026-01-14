from pathlib import Path

from pydantic import BaseModel


class CoverPhoto(BaseModel):
    uuid: str | None = None
    path: str | None = None


class Photo(BaseModel):
    path: Path
    width: int
    height: int

    @property
    def aspect_ratio(self) -> float:
        return float(self.width) / float(self.height)
