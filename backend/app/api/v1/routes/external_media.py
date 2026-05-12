from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.logic.external_media.operations import add_device_media
from app.logic.media_import import ImportCompleted, ImportContext, ImportRequest
from app.models.album import Album

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
