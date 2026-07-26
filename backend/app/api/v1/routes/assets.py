from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.locks import file_generation_lock
from app.core.worker_threads import run_sync
from app.logic.layout.media import (
    THUMB_WIDTHS,
    MediaName,
    delete_thumbnails,
    extract_frame,
    generate_thumbnail,
    is_video,
)
from app.logic.panorama.render import (
    PanoramaDestination,
    PanoramaRenderError,
    PanoramaValidationError,
    panorama_render_path,
    render_panorama,
    resolve_panorama_source,
)
from app.models.album_media import AlbumMedia, PanoramaConfig

from ..deps import SessionDep, UserDep, album_dir as _album_dir

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/albums", tags=["assets"])

# Photos and videos never change in-place -> cache forever.
_CACHE_IMMUTABLE = "public, max-age=31536000, immutable"
# Video posters (.jpg with a sibling .mp4) can change when the user
# picks a new frame, so the browser must revalidate on each load.
_CACHE_REVALIDATE = "public, no-cache"


class AssetQuery(BaseModel):
    w: int | None = None
    h: int | None = None
    panorama_revision: int | None = None


async def _ensure_media_source(source: Path, video: Path, name: str) -> str:
    is_poster = name.endswith(".jpg") and await run_sync(video.is_file)
    cache = _CACHE_REVALIDATE if is_poster else _CACHE_IMMUTABLE
    if not await run_sync(source.is_file) and is_poster:
        async with file_generation_lock(source):
            if not await run_sync(source.is_file):
                await extract_frame(video)
                logger.debug("asset.poster_extracted", media_name=name)
    if not await run_sync(source.is_file):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return cache


async def _render_rendition(
    source: Path,
    panorama: PanoramaConfig,
    destination: PanoramaDestination,
    rendition: Path,
) -> None:
    if await run_sync(rendition.is_file):
        return
    async with file_generation_lock(rendition):
        if await run_sync(rendition.is_file):
            return
        try:
            await render_panorama(source, panorama, destination, rendition)
        except PanoramaValidationError as error:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        except PanoramaRenderError as error:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Panorama rendering failed",
            ) from error


async def _panorama_rendition(
    media_key: tuple[int, str, str],
    session: SessionDep,
    album_dir: Path,
    query: AssetQuery,
) -> FileResponse:
    _uid, _aid, name = media_key
    width = query.w
    height = query.h
    revision = query.panorama_revision
    if width is None or height is None or revision is None or width <= 0 or height <= 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Positive panorama width and height are required",
        )
    media = await session.get(AlbumMedia, media_key)
    if (
        media is None
        or media.panorama is None
        or media.panorama.status != "active"
        or media.panorama.revision != revision
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        destination = PanoramaDestination(
            kind="asset",
            aspect_ratio=width / height,
            width_px=width,
            height_px=height,
        )
        source = resolve_panorama_source(album_dir, name, media.panorama)
    except ValueError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND) from error
    rendition = panorama_render_path(
        album_dir,
        name,
        revision,
        width,
        height,
    )
    await _render_rendition(source, media.panorama, destination, rendition)
    return FileResponse(
        rendition,
        media_type="image/jpeg",
        headers={"Cache-Control": _CACHE_IMMUTABLE},
    )


@router.get("/{aid}/media/{name}")
async def get_media(
    aid: str,
    name: MediaName,
    user: UserDep,
    session: SessionDep,
    query: Annotated[AssetQuery, Query()],
) -> FileResponse:
    album_dir = _album_dir(user, aid)
    source = album_dir / name
    video = album_dir / Path(name).with_suffix(".mp4")

    cache = await _ensure_media_source(source, video, name)

    if query.panorama_revision is not None:
        return await _panorama_rendition(
            (user.id, aid, name),
            session,
            album_dir,
            query,
        )

    # Lazy thumbnail generation.
    if query.w is not None and query.w in THUMB_WIDTHS:
        thumb = album_dir / ".thumbs" / str(query.w) / f"{Path(name).stem}.webp"
        if not thumb.is_file():
            async with file_generation_lock(thumb):
                if not thumb.is_file():
                    await generate_thumbnail(source, query.w)
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
