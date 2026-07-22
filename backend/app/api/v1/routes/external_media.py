import tempfile
from collections.abc import AsyncIterable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.sse import EventSourceResponse
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.logic.external_media.album_media import (
    MediaNotFoundError,
    replace_album_media_from_saved,
)
from app.logic.external_media.operations import (
    add_device_media,
    download_google_item_to_saved,
    download_google_items_to_saved,
    list_google_picker_items,
)
from app.logic.external_media.undo import (
    enqueue_undo_snapshot_prune,
    restore_undo_snapshot,
)
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

from ..deps import HttpClientsDep, SessionDep, UserDep, album_dir, require_loaded_user
from .google_photos import _ensure_fresh_access_token

router = APIRouter(prefix="/albums/{aid}/external-media", tags=["external-media"])


class GoogleImportRequest(ImportRequest):
    session_id: PickerSessionId


class GoogleReplaceRequest(BaseModel):
    media_name: MediaName
    session_id: PickerSessionId


@dataclass(frozen=True)
class GoogleImportContext:
    body: GoogleImportRequest
    album: Album
    album_dir: Path
    access_token: str
    validation_error: str | None = None


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


async def _load_google_import_context(
    request: Request,
    *,
    aid: str,
    body: GoogleImportRequest,
    background_tasks: BackgroundTasks,
    http: HttpClientsDep,
) -> GoogleImportContext:
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        user = await require_loaded_user(request, session, background_tasks)
        album = await _get_album_or_404(aid, user, session)
        _require_google_available(user)
        validation_error = None
        try:
            await validate_import_target(session, album=album, request=body)
        except ValueError as exc:
            validation_error = str(exc)
        access_token = await _ensure_fresh_access_token(http, user, session)
    return GoogleImportContext(
        body=body,
        album=album,
        album_dir=album_dir(user, aid),
        access_token=access_token,
        validation_error=validation_error,
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
async def replace_device(  # noqa: PLR0913
    aid: str,
    user: UserDep,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    media_name: Annotated[MediaName, Form()],
    file: Annotated[UploadFile, File()],
) -> AlbumMedia:
    album = await _get_album_or_404(aid, user, session)
    if await session.get(AlbumMedia, (user.id, aid, media_name)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
    target_album_dir = album_dir(user, aid)
    with tempfile.TemporaryDirectory(
        dir=target_album_dir,
        prefix=".replace-device-",
    ) as tmp:
        try:
            saved = await save_uploads([file], Path(tmp))
            if len(saved) != 1:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Select exactly one replacement",
                )
            row = await replace_album_media_from_saved(
                session,
                album=album,
                album_dir=target_album_dir,
                media_name=media_name,
                saved=saved[0],
            )
        except MediaNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
        except OverflowError as exc:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    await session.commit()
    enqueue_undo_snapshot_prune(background_tasks, user.id, aid, target_album_dir)
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
    context: Annotated[GoogleImportContext, Depends(_load_google_import_context)],
    http: HttpClientsDep,
) -> AsyncIterable[ImportEvent]:
    if context.validation_error is not None:
        yield ImportFailed(detail=context.validation_error)
        return
    async for event in _stream_google_import(context, context.body, http):
        yield event


async def _stream_google_import(
    context: GoogleImportContext,
    body: GoogleImportRequest,
    http: HttpClientsDep,
) -> AsyncIterable[ImportEvent]:
    written: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(
            dir=context.album_dir,
            prefix=".import-google-",
        ) as tmp:
            temp_dir = Path(tmp)
            saved = []
            async for item, saved_input in download_google_items_to_saved(
                http=http,
                access_token=context.access_token,
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
                album_dir=context.album_dir,
                saved=saved,
            )
            async with AsyncSession(get_engine(), expire_on_commit=False) as session:
                names = await persist_imported_media(
                    session,
                    album=context.album,
                    request=body,
                    imported=imported,
                    album_dir=context.album_dir,
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
async def replace_google_media(  # noqa: PLR0913
    aid: str,
    body: GoogleReplaceRequest,
    user: UserDep,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    http: HttpClientsDep,
) -> AlbumMedia:
    album = await _get_album_or_404(aid, user, session)
    _require_google_available(user)
    access_token = await _ensure_fresh_access_token(http, user, session)
    if await session.get(AlbumMedia, (user.id, aid, body.media_name)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media not found")
    target_album_dir = album_dir(user, aid)

    with tempfile.TemporaryDirectory(
        dir=target_album_dir,
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
                album_dir=target_album_dir,
                media_name=body.media_name,
                saved=saved,
            )
        except MediaNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    await session.commit()
    enqueue_undo_snapshot_prune(background_tasks, user.id, aid, target_album_dir)
    return row
