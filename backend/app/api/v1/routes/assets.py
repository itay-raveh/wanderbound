from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.logic.layout.media import (
    MediaName,
    extract_frame,
    generate_thumbnails,
    is_video,
)
from app.models.types import AlbumId
from app.models.user import User

from ..deps import UserDep

router = APIRouter(prefix="/albums", tags=["assets"])

# 1 year, immutable — media files never change in-place.  Video poster
# thumbnails are cache-busted by the frontend (?v=<timestamp>) after
# frame extraction, so they can use the same aggressive caching.
_CACHE_IMMUTABLE = "public, max-age=31536000, immutable"


def _resolve_media(user: User, aid: AlbumId, name: str) -> Path:
    resolved = (user.trips_folder / aid / name).resolve()
    if not resolved.is_relative_to(user.trips_folder / aid) or not resolved.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return resolved


@router.get("/{aid}/media/{name}")
async def get_media(
    aid: AlbumId,
    name: MediaName,
    user: UserDep,
    w: int | None = None,
) -> FileResponse:
    if w is not None:
        album_dir = user.trips_folder / aid
        thumb = album_dir / ".thumbs" / str(w) / f"{Path(name).stem}.webp"
        if thumb.is_file():
            return FileResponse(
                thumb,
                media_type="image/webp",
                headers={"Cache-Control": _CACHE_IMMUTABLE},
            )
        # Fall through to original if thumb doesn't exist
    return FileResponse(
        _resolve_media(user, aid, name),
        headers={"Cache-Control": _CACHE_IMMUTABLE},
    )


@router.patch("/{aid}/media/{name}")
async def update_video_frame(
    aid: AlbumId,
    name: MediaName,
    user: UserDep,
    timestamp: Annotated[float, Query()],
) -> None:
    if not is_video(name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a video")
    poster_path = await extract_frame(_resolve_media(user, aid, name), timestamp)
    await generate_thumbnails(poster_path)
