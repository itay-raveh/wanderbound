from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.core.worker_threads import run_sync
from app.logic.layout.media import MediaName, generation_lock
from app.logic.panorama import (
    PanoramaRenderError,
    PanoramaValidationError,
    create_panorama_source,
    panorama_render_path,
    panorama_source_path,
    remove_other_panorama_files,
    remove_panorama_derivatives,
    render_panorama,
    resolve_panorama_source,
)
from app.models.album_media import AlbumMedia, PanoramaConfig

from ..deps import SessionDep, UserDep, album_dir as _album_dir

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/albums", tags=["panoramas"])


async def _panorama_media(
    aid: str,
    name: str,
    user: UserDep,
    session: SessionDep,
    *,
    lock: bool = False,
) -> AlbumMedia:
    media = await session.get(
        AlbumMedia,
        (user.id, aid, name),
        with_for_update=lock,
    )
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not media.panorama_candidate:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Media is not a panorama",
        )
    return media


async def _render_or_error(
    media: AlbumMedia,
    config: PanoramaConfig,
    source: Path,
    output: Path,
) -> None:
    try:
        await render_panorama(
            source,
            config,
            output,
            (media.width, media.height),
        )
    except PanoramaValidationError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except PanoramaRenderError as error:
        logger.exception(
            "panorama.render_failed",
            user_id=media.uid,
            album_id=media.aid,
            media_name=media.name,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Panorama rendering failed",
        ) from error


def _source_or_404(album_dir: Path, name: str) -> Path:
    try:
        return resolve_panorama_source(album_dir, name)
    except FileNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND) from error


@router.put("/{aid}/media/{name}/panorama")
async def update_panorama(
    aid: str,
    name: MediaName,
    body: PanoramaConfig,
    user: UserDep,
    session: SessionDep,
) -> AlbumMedia:
    media = await _panorama_media(aid, name, user, session, lock=True)
    album_dir = _album_dir(user, aid)
    source = _source_or_404(album_dir, name)

    output = panorama_render_path(album_dir, name, source, body)
    output_existed = await run_sync(output.is_file)
    media.panorama = body
    await _render_or_error(media, body, source, output)
    try:
        media.updated_at = datetime.now(UTC)
        session.add(media)
        await session.commit()
    except BaseException:
        await session.rollback()
        if not output_existed:
            await run_sync(output.unlink, missing_ok=True)
        raise

    await run_sync(remove_other_panorama_files, output)
    await session.refresh(media)
    return media


@router.delete("/{aid}/media/{name}/panorama")
async def disable_panorama(
    aid: str,
    name: MediaName,
    user: UserDep,
    session: SessionDep,
) -> AlbumMedia:
    media = await _panorama_media(aid, name, user, session, lock=True)
    if media.panorama is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST)
    media.panorama = None
    media.updated_at = datetime.now(UTC)
    session.add(media)
    await session.commit()
    await run_sync(remove_panorama_derivatives, _album_dir(user, aid), name)
    await session.refresh(media)
    return media


@router.get("/{aid}/media/{name}/panorama-source")
async def get_panorama_source(
    aid: str,
    name: MediaName,
    user: UserDep,
    session: SessionDep,
) -> FileResponse:
    media = await _panorama_media(aid, name, user, session)
    album_dir = _album_dir(user, aid)
    source = _source_or_404(album_dir, name)
    output = panorama_source_path(album_dir, name, source)
    async with generation_lock(output):
        if not await run_sync(output.is_file):
            await create_panorama_source(source, output, media.width, media.height)
    await run_sync(remove_other_panorama_files, output)
    return FileResponse(
        output,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, no-cache"},
    )


@router.get("/{aid}/media/{name}/panorama-render")
async def get_panorama_render(
    aid: str,
    name: MediaName,
    user: UserDep,
    session: SessionDep,
) -> FileResponse:
    media = await _panorama_media(aid, name, user, session)
    if media.panorama is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    album_dir = _album_dir(user, aid)
    source = _source_or_404(album_dir, name)
    output = panorama_render_path(album_dir, name, source, media.panorama)
    async with generation_lock(output):
        if not await run_sync(output.is_file):
            await _render_or_error(media, media.panorama, source, output)
    await run_sync(remove_other_panorama_files, output)
    return FileResponse(
        output,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, no-cache"},
    )
