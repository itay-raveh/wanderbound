from __future__ import annotations

from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.worker_threads import run_sync
from app.logic.layout.media import MediaName
from app.logic.panorama.render import (
    PanoramaDestination,
    PanoramaFrameUpdate,
    PanoramaRenderError,
    PanoramaValidationError,
    create_panorama_preview,
    panorama_preview_path,
    panorama_render_path,
    render_panorama,
    resolve_panorama_source,
    validate_panorama_frame,
)
from app.logic.panorama.storage import (
    remove_obsolete_render_revisions,
    remove_panorama_derivatives,
)
from app.models.album_media import (
    MAX_CAPTURED_FOV,
    MIN_CAPTURED_FOV,
    AlbumMedia,
    PanoramaConfig,
)

from ..deps import SessionDep, UserDep, album_dir as _album_dir

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/albums", tags=["panoramas"])


class PanoramaApply(BaseModel):
    frame: PanoramaFrameUpdate
    destination: PanoramaDestination


async def _locked_media(
    aid: str,
    name: str,
    user: UserDep,
    session: SessionDep,
) -> AlbumMedia:
    media = await session.get(
        AlbumMedia,
        (user.id, aid, name),
        with_for_update=True,
    )
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if media.panorama is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Media has no panorama configuration",
        )
    return media


@router.put("/{aid}/media/{name}/panorama")
async def update_panorama(
    aid: str,
    name: MediaName,
    body: PanoramaApply,
    user: UserDep,
    session: SessionDep,
) -> AlbumMedia:
    media = await _locked_media(aid, name, user, session)
    current = media.panorama
    if current is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST)
    if (
        current.detection == "gpano"
        and body.frame.captured_fov is not None
        and body.frame.captured_fov != current.captured_fov
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Captured FOV cannot override GPano metadata",
        )

    proposed_values = current.model_dump() | body.frame.model_dump(exclude_none=True)
    proposed_values.update(status="active", revision=current.revision + 1)
    proposed = PanoramaConfig.model_validate(proposed_values)
    try:
        validate_panorama_frame(proposed, body.destination)
    except PanoramaValidationError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    album_dir = _album_dir(user, aid)
    try:
        source = resolve_panorama_source(album_dir, name, proposed)
    except FileNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND) from error
    derivative = panorama_render_path(
        album_dir,
        name,
        proposed.revision,
        body.destination.width_px,
        body.destination.height_px,
    )
    configuration_staged = False
    try:
        await _render_derivative(
            source,
            proposed,
            body.destination,
            derivative,
            media,
        )
        configuration_staged = True
        media.panorama = proposed
        session.add(media)
        await session.commit()
    except BaseException:
        await _discard_update(
            session,
            derivative,
            media,
            rollback=configuration_staged,
        )
        raise
    await run_sync(
        remove_obsolete_render_revisions,
        album_dir,
        name,
        proposed.revision,
    )
    await session.refresh(media)
    return media


async def _render_derivative(
    source: Path,
    config: PanoramaConfig,
    destination: PanoramaDestination,
    derivative: Path,
    media: AlbumMedia,
) -> None:
    try:
        await render_panorama(source, config, destination, derivative)
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


async def _discard_update(
    session: SessionDep,
    derivative: Path,
    media: AlbumMedia,
    *,
    rollback: bool,
) -> None:
    if rollback:
        try:
            await session.rollback()
        except BaseException:
            logger.exception(
                "panorama.rollback_failed",
                user_id=media.uid,
                album_id=media.aid,
                media_name=media.name,
            )
    try:
        await run_sync(derivative.unlink, missing_ok=True)
    except OSError:
        logger.exception(
            "panorama.cleanup_failed",
            user_id=media.uid,
            album_id=media.aid,
            media_name=media.name,
        )


@router.delete("/{aid}/media/{name}/panorama")
async def disable_panorama(
    aid: str,
    name: MediaName,
    user: UserDep,
    session: SessionDep,
) -> AlbumMedia:
    media = await _locked_media(aid, name, user, session)
    current = media.panorama
    if current is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST)
    media.panorama = PanoramaConfig.model_validate(
        current.model_dump() | {"status": "disabled", "revision": current.revision + 1}
    )
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
    captured_fov: Annotated[
        int | None,
        Query(ge=MIN_CAPTURED_FOV, le=MAX_CAPTURED_FOV),
    ] = None,
) -> FileResponse:
    media = await session.get(AlbumMedia, (user.id, aid, name))
    if media is None or media.panorama is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    config = media.panorama
    if captured_fov is not None:
        if config.detection == "gpano" and captured_fov != config.captured_fov:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Captured FOV cannot override GPano metadata",
            )
        config = config.model_copy(update={"captured_fov": captured_fov})
    album_dir = _album_dir(user, aid)
    try:
        source = resolve_panorama_source(album_dir, name, config)
    except FileNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND) from error
    preview = panorama_preview_path(album_dir, name, source, config)
    if not preview.is_file():
        await create_panorama_preview(source, config, preview)
    return FileResponse(
        preview,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, no-cache"},
    )
