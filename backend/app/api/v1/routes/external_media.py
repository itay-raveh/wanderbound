import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.logic.external_media.album_media import replace_album_media_from_saved
from app.logic.external_media.operations import add_device_media
from app.logic.external_media.undo import restore_undo_snapshot
from app.logic.layout.media import MediaName
from app.logic.media_import import (
    ImportCompleted,
    ImportContext,
    ImportRequest,
    save_uploads,
)
from app.models.album import Album
from app.models.album_media import AlbumMedia

from ..deps import SessionDep, UserDep, album_dir

router = APIRouter(prefix="/albums/{aid}/external-media", tags=["external-media"])


async def _get_album_or_404(aid: str, user: UserDep, session: SessionDep) -> Album:
    album = await session.get(Album, (user.id, aid))
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Album not found")
    return album


@router.post("/add/device")
async def add_device(  # noqa: PLR0913
    aid: str,
    user: UserDep,
    session: SessionDep,
    context: Annotated[ImportContext, Form()],
    files: Annotated[list[UploadFile], File()],
    step_id: Annotated[int | None, Form()] = None,
) -> ImportCompleted:
    album = await _get_album_or_404(aid, user, session)
    try:
        names = await add_device_media(
            session,
            album=album,
            album_dir=album_dir(user, aid),
            request=ImportRequest(context=context, step_id=step_id),
            files=files,
        )
    except OverflowError as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return ImportCompleted(names=names)


@router.post("/replace/device")
async def replace_device(
    aid: str,
    user: UserDep,
    session: SessionDep,
    media_name: Annotated[MediaName, Form()],
    file: Annotated[UploadFile, File()],
) -> AlbumMedia:
    album = await _get_album_or_404(aid, user, session)
    with tempfile.TemporaryDirectory(
        dir=album_dir(user, aid),
        prefix=".replace-device-",
    ) as tmp:
        saved = await save_uploads([file], Path(tmp))
        if len(saved) != 1:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Select exactly one replacement",
            )
        try:
            row = await replace_album_media_from_saved(
                session,
                album=album,
                album_dir=album_dir(user, aid),
                media_name=media_name,
                saved=saved[0],
                source_ref_id=None,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    await session.commit()
    return row


@router.post("/undo/{media_name}")
async def undo_replacement(
    aid: str,
    media_name: MediaName,
    user: UserDep,
    session: SessionDep,
) -> AlbumMedia:
    album = await _get_album_or_404(aid, user, session)
    try:
        row = await restore_undo_snapshot(
            session,
            album=album,
            album_dir=album_dir(user, aid),
            media_name=media_name,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    await session.commit()
    return row
