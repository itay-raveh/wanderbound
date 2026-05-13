import tempfile
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel

from app.logic.external_media.album_media import replace_album_media_from_saved
from app.logic.external_media.operations import (
    add_device_media,
    download_google_item_to_saved,
    download_google_items_to_saved,
    list_google_picker_items,
)
from app.logic.external_media.undo import restore_undo_snapshot
from app.logic.layout.media import MediaName
from app.logic.media_import import (
    ImportCompleted,
    ImportContext,
    ImportEvent,
    ImportFailed,
    ImportInProgress,
    ImportRequest,
    cleanup_imported_paths,
    persist_imported_media,
    process_saved_media,
    save_uploads,
    validate_import_target,
)
from app.models.album import Album
from app.models.album_media import AlbumMedia
from app.models.google_photos import PickerSessionId
from app.services.google_photos import DownloadTooLargeError

from ..deps import HttpClientsDep, SessionDep, UserDep, album_dir
from .google_photos import _ensure_fresh_access_token

router = APIRouter(prefix="/albums/{aid}/external-media", tags=["external-media"])


class GoogleImportRequest(ImportRequest):
    session_id: PickerSessionId


class GoogleReplaceRequest(BaseModel):
    media_name: MediaName
    session_id: PickerSessionId


async def _get_album_or_404(aid: str, user: UserDep, session: SessionDep) -> Album:
    album = await session.get(Album, (user.id, aid))
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Album not found")
    return album


def _require_google_available(user: UserDep) -> None:
    if not user.google_sub:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Google Photos import requires a Google account",
        )
    if user.google_photos_connected_at is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Google Photos not connected. Please authorize first.",
        )


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


@router.post(
    "/add/google",
    response_class=EventSourceResponse,
    responses={200: {"model": list[ImportEvent]}},
)
async def add_google_media(
    aid: str,
    body: GoogleImportRequest,
    user: UserDep,
    session: SessionDep,
    http: HttpClientsDep,
) -> AsyncIterable[ImportEvent]:
    album = await _get_album_or_404(aid, user, session)
    _require_google_available(user)
    access_token = await _ensure_fresh_access_token(http, user)
    try:
        await validate_import_target(session, album=album, request=body)
    except ValueError as exc:
        yield ImportFailed(detail=str(exc))
        return
    written: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(
            dir=album_dir(user, aid),
            prefix=".import-google-",
        ) as tmp:
            temp_dir = Path(tmp)
            saved = []
            async for item, saved_input in download_google_items_to_saved(
                http=http,
                access_token=access_token,
                session_id=body.session_id,
                temp_dir=temp_dir,
            ):
                del item
                saved.append(saved_input)
                yield ImportInProgress(
                    phase="downloading",
                    done=len(saved),
                    total=0,
                )
            imported, written = await process_saved_media(
                album_dir=album_dir(user, aid),
                saved=saved,
            )
            names = await persist_imported_media(
                session,
                album=album,
                request=body,
                imported=imported,
                album_dir=album_dir(user, aid),
            )
            written = []
            yield ImportCompleted(names=names)
    except (OverflowError, DownloadTooLargeError) as exc:
        await cleanup_imported_paths(written)
        yield ImportFailed(detail=str(exc))
    except ValueError as exc:
        await cleanup_imported_paths(written)
        yield ImportFailed(detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        del exc
        await cleanup_imported_paths(written)
        yield ImportFailed(detail="Media import failed unexpectedly.")
    except BaseException:
        await cleanup_imported_paths(written)
        raise


@router.post("/replace/google")
async def replace_google_media(
    aid: str,
    body: GoogleReplaceRequest,
    user: UserDep,
    session: SessionDep,
    http: HttpClientsDep,
) -> AlbumMedia:
    album = await _get_album_or_404(aid, user, session)
    _require_google_available(user)
    access_token = await _ensure_fresh_access_token(http, user)
    if await session.get(AlbumMedia, (user.id, aid, body.media_name)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")

    with tempfile.TemporaryDirectory(
        dir=album_dir(user, aid),
        prefix=".replace-google-",
    ) as tmp:
        picked_items = await list_google_picker_items(
            http=http,
            access_token=access_token,
            session_id=body.session_id,
        )
        if len(picked_items) != 1:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Select exactly one replacement",
            )
        try:
            saved = await download_google_item_to_saved(
                http=http,
                access_token=access_token,
                item=picked_items[0],
                temp_dir=Path(tmp),
            )
        except (OverflowError, DownloadTooLargeError) as exc:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from None
        try:
            row = await replace_album_media_from_saved(
                session,
                album=album,
                album_dir=album_dir(user, aid),
                media_name=body.media_name,
                saved=saved,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    await session.commit()
    return row
