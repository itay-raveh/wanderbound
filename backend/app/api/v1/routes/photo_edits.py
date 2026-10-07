from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.logic.layout.media import MediaName, open_oriented
from app.logic.photo_edit import validate_photo_edit
from app.models.album_media import AlbumMedia, PhotoEdit

from ..deps import SessionDep, UserDep, album_dir as _album_dir
from .panoramas import current_panorama_render

router = APIRouter(prefix="/albums", tags=["photo-edits"])


async def _photo(aid: str, name: str, user: UserDep, session: SessionDep) -> AlbumMedia:
    media = await session.get(AlbumMedia, (user.id, aid, name), with_for_update=True)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if media.kind != "photo":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Media is not a photo")
    return media


@router.get("/{aid}/media/{name}/photo-source")
async def get_photo_source(
    aid: str,
    name: MediaName,
    user: UserDep,
    session: SessionDep,
) -> FileResponse:
    media = await _photo(aid, name, user, session)
    album_dir = _album_dir(user, aid)
    source = (
        await current_panorama_render(media, album_dir)
        if media.panorama is not None
        else album_dir / name
    )
    if not source.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return FileResponse(source, headers={"Cache-Control": "public, no-cache"})


@router.put("/{aid}/media/{name}/photo-edit")
async def update_photo_edit(
    aid: str,
    name: MediaName,
    body: PhotoEdit,
    user: UserDep,
    session: SessionDep,
) -> AlbumMedia:
    media = await _photo(aid, name, user, session)
    album_dir = _album_dir(user, aid)
    source = (
        await current_panorama_render(media, album_dir)
        if media.panorama is not None
        else album_dir / name
    )
    if not source.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    with open_oriented(source) as image:
        try:
            validate_photo_edit(body, *image.size)
        except ValueError as error:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail=str(error)
            ) from error
    media.photo_edit = body
    media.updated_at = datetime.now(UTC)
    session.add(media)
    await session.commit()
    await session.refresh(media)
    return media


@router.delete("/{aid}/media/{name}/photo-edit")
async def reset_photo_edit(
    aid: str,
    name: MediaName,
    user: UserDep,
    session: SessionDep,
) -> AlbumMedia:
    media = await _photo(aid, name, user, session)
    media.photo_edit = None
    media.updated_at = datetime.now(UTC)
    session.add(media)
    await session.commit()
    await session.refresh(media)
    return media
