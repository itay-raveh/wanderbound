from __future__ import annotations

import tempfile
from collections.abc import AsyncIterable, AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel

from app.logic.media_import import (
    MAX_IMPORT_ITEMS,
    MAX_PHOTO_BYTES,
    MAX_VIDEO_BYTES,
    ImportCompleted,
    ImportContext,
    ImportEvent,
    ImportFailed,
    ImportInProgress,
    ImportRequest,
    SavedInput,
    import_saved_media,
    import_upload_files,
)
from app.models.album import Album
from app.models.google_photos import PickerSessionId
from app.services.google_photos import (
    create_picker_session,
    download_media_to_file,
    get_media_items,
)

from ..deps import HttpClientsDep, SessionDep, UserDep, album_dir
from .google_photos import _ensure_fresh_access_token

router = APIRouter(prefix="/albums/{aid}/media-imports", tags=["media-imports"])


class PickerSessionResponse(BaseModel):
    session_id: PickerSessionId
    picker_uri: str


class GoogleImportRequest(ImportRequest):
    session_id: PickerSessionId


async def _get_album_or_404(aid: str, user: UserDep, session: SessionDep) -> Album:
    album = await session.get(Album, (user.id, aid))
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Album not found")
    return album


def _require_google_import_available(user: UserDep) -> None:
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


GoogleImportAlbumDep = Annotated[Album, Depends(_get_album_or_404)]


async def _get_google_import_access_token(
    user: UserDep,
    http: HttpClientsDep,
) -> str:
    _require_google_import_available(user)
    return await _ensure_fresh_access_token(http, user)


GoogleImportAccessTokenDep = Annotated[str, Depends(_get_google_import_access_token)]


@router.post("/device")
async def import_device_media(  # noqa: PLR0913
    aid: str,
    user: UserDep,
    session: SessionDep,
    context: Annotated[ImportContext, Form()],
    files: Annotated[list[UploadFile], File()],
    step_id: Annotated[int | None, Form()] = None,
) -> ImportCompleted:
    album = await _get_album_or_404(aid, user, session)
    try:
        request = ImportRequest(context=context, step_id=step_id)
        names = await import_upload_files(
            session,
            album=album,
            album_dir=album_dir(user, aid),
            request=request,
            files=files,
        )
    except OverflowError as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return ImportCompleted(names=names)


@router.post("/google/session")
async def create_google_import_session(
    aid: str,
    user: UserDep,
    session: SessionDep,
    http: HttpClientsDep,
) -> PickerSessionResponse:
    await _get_album_or_404(aid, user, session)
    _require_google_import_available(user)
    access_token = await _ensure_fresh_access_token(http, user)
    picker = await create_picker_session(
        http.gphotos_picker,
        access_token,
        max_item_count=MAX_IMPORT_ITEMS,
    )
    return PickerSessionResponse(session_id=picker.id, picker_uri=picker.picker_uri)


async def _download_google_items(
    *,
    http: HttpClientsDep,
    access_token: str,
    session_id: PickerSessionId,
    temp_dir: Path,
) -> AsyncIterator[SavedInput]:
    items = await get_media_items(http.gphotos_picker, session_id, access_token)
    if len(items) > MAX_IMPORT_ITEMS:
        raise OverflowError("Too many files")

    total = 0
    for index, item in enumerate(items):
        path = temp_dir / f"google-{index}"
        max_bytes = MAX_VIDEO_BYTES if item.type == "VIDEO" else MAX_PHOTO_BYTES
        await download_media_to_file(
            http.gphotos_picker,
            item.media_file.base_url,
            access_token,
            path,
            max_bytes=max_bytes,
        )
        size = path.stat().st_size
        total += size
        if total > MAX_VIDEO_BYTES:
            raise OverflowError("Import is too large")
        yield SavedInput(path=path, size=size)


@router.post(
    "/google",
    response_class=EventSourceResponse,
    responses={200: {"model": list[ImportEvent]}},
)
async def import_google_media(  # noqa: PLR0913
    aid: str,
    body: GoogleImportRequest,
    user: UserDep,
    session: SessionDep,
    http: HttpClientsDep,
    album: GoogleImportAlbumDep,
    access_token: GoogleImportAccessTokenDep,
) -> AsyncIterable[ImportEvent]:
    try:
        with tempfile.TemporaryDirectory(
            dir=album_dir(user, aid), prefix=".import-google-"
        ) as tmp:
            temp_dir = Path(tmp)
            saved: list[SavedInput] = []
            async for item in _download_google_items(
                http=http,
                access_token=access_token,
                session_id=body.session_id,
                temp_dir=temp_dir,
            ):
                saved.append(item)
                yield ImportInProgress(
                    phase="downloading",
                    done=len(saved),
                    total=0,
                )

            names = await import_saved_media(
                session,
                album=album,
                album_dir=album_dir(user, aid),
                request=body,
                saved=saved,
            )
            yield ImportCompleted(names=names)
    except OverflowError as exc:
        yield ImportFailed(detail=str(exc))
    except Exception:  # noqa: BLE001
        yield ImportFailed(detail="Media import failed unexpectedly.")
