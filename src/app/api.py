from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.app.engine import AlbumService, get_album_service
from src.models.layout import StepLayout

api_router = APIRouter()


class CoverRequest(BaseModel):
    id: int
    cover: str


class VideoUpdateRequest(BaseModel):
    id: int
    src: str
    timestamp: float


class LayoutRequest(BaseModel):
    updates: list[StepLayout]


Service = Annotated[AlbumService, Depends(get_album_service, use_cache=False)]


@api_router.post("/cover")
async def handle_cover(cover_request: CoverRequest, service: Service) -> None:
    await service.update_cover(cover_request.id, cover_request.cover)


@api_router.post("/video")
async def handle_video(video_request: VideoUpdateRequest, service: Service) -> None:
    await service.update_video_timestamp(
        video_request.id, video_request.src, video_request.timestamp
    )


@api_router.post("/layout")
async def handle_layout(layout_request: LayoutRequest, service: Service) -> None:
    await service.update_layout(layout_request.updates)
