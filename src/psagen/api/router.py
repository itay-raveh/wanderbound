from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from nicegui import app
from pydantic import BaseModel

from psagen.logic.album import Album
from psagen.models.layout import StepLayout
from psagen.models.user import TripName, User

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


ALBUMS: dict[TripName, Album] = {}

DependsUser = Annotated[User, Depends(User.from_storage)]


def get_current_album(user: DependsUser) -> Album:
    return ALBUMS[user.selected_trip]


DependsAlbum = Annotated[Album, Depends(get_current_album)]


@api_router.post("/cover")
async def handle_cover(cover_request: CoverRequest, album: DependsAlbum) -> None:
    await album.update_cover(cover_request.id, cover_request.cover)


@api_router.post("/video")
async def handle_video(video_request: VideoUpdateRequest, album: DependsAlbum) -> None:
    await album.update_video_timestamp(video_request.id, video_request.src, video_request.timestamp)


@api_router.post("/layout")
async def handle_layout(layout_request: LayoutRequest, album: DependsAlbum) -> None:
    await album.update_layout(layout_request.updates)


@app.get("/trip/{path:path}")
async def serve_asset(path: str, user: DependsUser) -> Response:
    file = user.trips_folder / path

    # Prevent path traversal (ensure path is within session dir)
    try:
        await file.resolve(strict=True)
    except ValueError:
        raise HTTPException(  # noqa: B904
            status_code=403, detail="Access denied: path traversal detected"
        )

    # Check file exists
    if not await file.is_file():
        return Response(content="File not found", media_type="text/plain", status_code=404)

    return FileResponse(file)
