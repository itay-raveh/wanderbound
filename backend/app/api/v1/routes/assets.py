import asyncio
import logging
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.logic.layout.media import (
    THUMB_WIDTHS,
    MediaName,
    delete_thumbnails,
    extract_frame,
    generate_thumbnail,
    is_video,
)
from app.models.user import User

from ..deps import UserDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/albums", tags=["assets"])

# Photos and videos never change in-place -> cache forever.
_CACHE_IMMUTABLE = "public, max-age=31536000, immutable"
# Video posters (.jpg with a sibling .mp4) can change when the user
# picks a new frame, so the browser must revalidate on each load.
_CACHE_REVALIDATE = "public, no-cache"

# Deduplicates concurrent lazy generation of the same file (poster or thumbnail).
# WeakValueDictionary auto-collects locks when no coroutine holds a reference,
# avoiding the race where manual cleanup deletes a lock while a waiter exists.
_gen_locks: weakref.WeakValueDictionary[Path, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)


@asynccontextmanager
async def _gen_lock(path: Path) -> AsyncIterator[None]:
    lock = _gen_locks.get(path)
    if lock is None:
        lock = asyncio.Lock()
        _gen_locks[path] = lock
    async with lock:
        yield


def _album_dir(user: User, aid: str) -> Path:
    """Resolve the album directory, rejecting path traversal in ``aid``."""
    resolved = (user.trips_folder / aid).resolve()
    if not resolved.is_relative_to(user.trips_folder):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return resolved


@router.get("/{aid}/media/{name}")
async def get_media(
    aid: str,
    name: MediaName,
    user: UserDep,
    w: int | None = None,
) -> FileResponse:
    album_dir = _album_dir(user, aid)
    source = album_dir / name
    video = album_dir / Path(name).with_suffix(".mp4")

    # Video posters (.jpg with a sibling .mp4) can be re-extracted by the user.
    is_poster = name.endswith(".jpg") and video.is_file()
    cache = _CACHE_REVALIDATE if is_poster else _CACHE_IMMUTABLE

    # Lazy poster extraction: .jpg requested but only the .mp4 exists.
    if not source.is_file() and is_poster:
        async with _gen_lock(source):
            if not source.is_file():
                await extract_frame(video)
                logger.debug("Lazy-extracted poster for %s", name)

    if not source.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    # Lazy thumbnail generation.
    if w is not None and w in THUMB_WIDTHS:
        thumb = album_dir / ".thumbs" / str(w) / f"{Path(name).stem}.webp"
        if not thumb.is_file():
            async with _gen_lock(thumb):
                if not thumb.is_file():
                    await generate_thumbnail(source, w)
        if thumb.is_file():
            return FileResponse(
                thumb,
                media_type="image/webp",
                headers={"Cache-Control": cache},
            )

    return FileResponse(
        source.resolve(),
        headers={"Cache-Control": cache},
    )


@router.patch("/{aid}/media/{name}")
async def update_video_frame(
    aid: str,
    name: MediaName,
    user: UserDep,
    timestamp: Annotated[float, Query()],
) -> None:
    if not is_video(name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Not a video")
    album_dir = _album_dir(user, aid)
    video = album_dir / name
    if not video.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    poster = video.with_suffix(".jpg")
    # Delete stale poster and its thumbnails before re-extracting.
    poster.unlink(missing_ok=True)
    delete_thumbnails(poster)
    await extract_frame(video, timestamp)
    logger.debug("Re-extracted frame for %s at t=%.1fs", name, timestamp)
