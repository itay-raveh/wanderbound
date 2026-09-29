from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.core.worker_threads import run_sync
from app.logic.layout.media import (
    THUMB_WIDTHS,
    MediaName,
    delete_thumbnails,
    extract_frame,
    generate_thumbnail,
    generation_lock,
    is_video,
)
from app.logic.photo_edit import render_photo_edit
from app.models.album_media import AlbumMedia

from ..deps import SessionDep, UserDep, album_dir as _album_dir
from .panoramas import current_panorama_render

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/albums", tags=["assets"])

# Photos and videos never change in-place -> cache forever.
_CACHE_IMMUTABLE = "public, max-age=31536000, immutable"
# Video posters (.jpg with a sibling .mp4) can change when the user
# picks a new frame, so the browser must revalidate on each load.
_CACHE_REVALIDATE = "public, no-cache"


async def _edited_source(
    source: Path, aid: str, name: str, user: UserDep, session: SessionDep
) -> Path:
    media = await session.get(AlbumMedia, (user.id, aid, name))
    if media is None or media.photo_edit is None:
        return source
    if media.panorama is not None:
        source = await current_panorama_render(media, _album_dir(user, aid))
    return await render_photo_edit(_album_dir(user, aid), source, media.photo_edit)


async def _ensure_poster(source: Path, video: Path, name: str) -> None:
    if await run_sync(source.is_file) or not await run_sync(video.is_file):
        return
    async with generation_lock(source):
        if not await run_sync(source.is_file):
            await extract_frame(video)
            logger.debug("asset.poster_extracted", media_name=name)


@router.get("/{aid}/media/{name}")
async def get_media(
    aid: str,
    name: MediaName,
    user: UserDep,
    session: SessionDep,
    w: int | None = None,
) -> FileResponse:
    album_dir = _album_dir(user, aid)
    source = album_dir / name
    video = album_dir / Path(name).with_suffix(".mp4")

    # Video posters (.jpg with a sibling .mp4) can be re-extracted by the user.
    is_poster = name.endswith(".jpg") and video.is_file()
    cache = _CACHE_REVALIDATE if is_poster else _CACHE_IMMUTABLE

    # Lazy poster extraction: .jpg requested but only the .mp4 exists.
    if is_poster:
        await _ensure_poster(source, video, name)

    if not source.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    edited = await _edited_source(source, aid, name, user, session)
    if edited != source:
        source = edited
        cache = _CACHE_REVALIDATE

    # Lazy thumbnail generation.
    if w is not None and w in THUMB_WIDTHS:
        thumb = source.parent / ".thumbs" / str(w) / f"{source.stem}.webp"
        if not thumb.is_file():
            async with generation_lock(thumb):
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
    logger.debug("asset.frame_reextracted", media_name=name, timestamp_s=timestamp)
