import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.logic.layout.media import (
    THUMB_WIDTHS,
    MediaName,
    extract_frame,
    generate_thumbnails,
    is_video,
)
from app.models.types import AlbumId
from app.models.user import User

from ..deps import UserDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/albums", tags=["assets"])

# Photos and videos never change in-place → cache forever.
_CACHE_IMMUTABLE = "public, max-age=31536000, immutable"
# Video posters (.jpg with a sibling .mp4) can change when the user
# picks a new frame, so the browser must revalidate on each load.
_CACHE_REVALIDATE = "public, no-cache"


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
    album_dir = user.trips_folder / aid
    # Video posters (.jpg with a sibling .mp4) can be re-extracted by the user.
    is_poster = (
        name.endswith(".jpg") and (album_dir / Path(name).with_suffix(".mp4")).is_file()
    )
    cache = _CACHE_REVALIDATE if is_poster else _CACHE_IMMUTABLE

    if w is not None and w in THUMB_WIDTHS:
        thumb = album_dir / ".thumbs" / str(w) / f"{Path(name).stem}.webp"
        if thumb.is_file():
            return FileResponse(
                thumb,
                media_type="image/webp",
                headers={"Cache-Control": cache},
            )
    return FileResponse(
        _resolve_media(user, aid, name),
        headers={"Cache-Control": cache},
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
    logger.info("Re-extracted frame for %s at t=%.1fs", name, timestamp)
