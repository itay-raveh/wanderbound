from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.logic.layout.media import MediaName, extract_frame, is_video
from app.models.types import AlbumId
from app.models.user import User

from ..deps import UserDep

router = APIRouter(prefix="/albums", tags=["assets"])


def _resolve_media(user: User, aid: AlbumId, name: str) -> Path:
    resolved = (user.trips_folder / aid / name).resolve()
    if not resolved.is_relative_to(user.trips_folder / aid) or not resolved.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return resolved


@router.get("/{aid}/media/{name}")
async def get_media(aid: AlbumId, name: MediaName, user: UserDep) -> FileResponse:
    return FileResponse(_resolve_media(user, aid, name))


@router.patch("/{aid}/media/{name}")
async def update_video_frame(
    aid: AlbumId,
    name: MediaName,
    user: UserDep,
    timestamp: Annotated[float, Query()],
) -> None:
    if not is_video(name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a video")
    await extract_frame(_resolve_media(user, aid, name), timestamp)
