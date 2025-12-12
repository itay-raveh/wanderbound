from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class CoverPhoto(BaseModel):
    uuid: str | None = None
    url: str | None = Field(default=None, alias="path")


class Photo(BaseModel):
    id: str
    index: int = Field(..., gt=0)
    path: Path
    width: int | None = Field(None, gt=0)
    height: int | None = Field(None, gt=0)
    aspect_ratio: float | None = Field(None, gt=0)


PhotoLayout = Literal["three-portraits", "portrait-landscape-split"]


class AssetPhoto(BaseModel):
    id: str
    path: Path


class PhotoPageData(BaseModel):
    photos: list[AssetPhoto]
    layout_class: PhotoLayout | None = None
    grid_style: str | None = None


class AlbumPhotoData(BaseModel):
    steps_with_photos: dict[int, list[Photo]]
    steps_cover_photos: dict[int, Photo | None]
    steps_photo_pages: dict[int, list[list[Photo]]]
    steps_hidden_photos: dict[int, list[Photo]] = Field(default_factory=dict)
