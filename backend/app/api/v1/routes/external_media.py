import tempfile
from collections.abc import AsyncIterable
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel
from sqlmodel import select

from app.logic.external_media.album_media import replace_album_media_from_saved
from app.logic.external_media.operations import (
    add_device_media,
    download_google_items_to_saved,
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
)
from app.models.album import Album
from app.models.album_media import AlbumMedia, AlbumMediaSourceKind, AlbumMediaSourceRef
from app.models.google_photos import PickedMediaItem, PickerSessionId
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


async def _ensure_google_source_ref(
    session: SessionDep,
    *,
    uid: int,
    aid: str,
    item: PickedMediaItem,
) -> AlbumMediaSourceRef:
    existing = (
        await session.exec(
            select(AlbumMediaSourceRef).where(
                AlbumMediaSourceRef.uid == uid,
                AlbumMediaSourceRef.aid == aid,
                AlbumMediaSourceRef.source_kind == AlbumMediaSourceKind.google_photos,
                AlbumMediaSourceRef.google_media_id == item.id,
            )
        )
    ).first()
    if existing is not None:
        return existing
    ref = AlbumMediaSourceRef(
        uid=uid,
        aid=aid,
        source_kind=AlbumMediaSourceKind.google_photos,
        google_media_id=item.id,
        mime_type=item.media_file.mime_type,
        width=item.media_file.width,
        height=item.media_file.height,
        captured_at=_captured_at(item),
    )
    session.add(ref)
    await session.flush()
    return ref


def _captured_at(item: PickedMediaItem) -> datetime | None:
    try:
        return datetime.fromisoformat(item.create_time)
    except ValueError:
        return None


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

    with tempfile.TemporaryDirectory(
        dir=album_dir(user, aid),
        prefix=".replace-google-",
    ) as tmp:
        saved_items = [
            item
            async for item in download_google_items_to_saved(
                http=http,
                access_token=access_token,
                session_id=body.session_id,
                temp_dir=Path(tmp),
            )
        ]
        if len(saved_items) != 1:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Select exactly one replacement",
            )
        picked_item, saved = saved_items[0]
        source_ref = await _ensure_google_source_ref(
            session,
            uid=user.id,
            aid=aid,
            item=picked_item,
        )
        try:
            row = await replace_album_media_from_saved(
                session,
                album=album,
                album_dir=album_dir(user, aid),
                media_name=body.media_name,
                saved=saved,
                source_ref_id=source_ref.id,
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    await session.commit()
    return row
