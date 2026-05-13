from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

from app.logic.layout.media import MediaName
from app.logic.media_import import (
    MAX_IMPORT_ITEMS,
    MAX_PHOTO_BYTES,
    MAX_VIDEO_BYTES,
    ImportRequest,
    SavedInput,
    import_upload_files,
)
from app.models.album import Album
from app.models.google_photos import PickedMediaItem, PickerSessionId
from app.services.google_photos import download_media_to_file, get_media_items

if TYPE_CHECKING:
    from fastapi import UploadFile
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.http_clients import HttpClients


async def add_device_media(
    session: AsyncSession,
    *,
    album: Album,
    album_dir: Path,
    request: ImportRequest,
    files: list[UploadFile],
) -> list[MediaName]:
    return await import_upload_files(
        session,
        album=album,
        album_dir=album_dir,
        request=request,
        files=files,
    )


async def download_google_items_to_saved(
    *,
    http: HttpClients,
    access_token: str,
    session_id: PickerSessionId,
    temp_dir: Path,
) -> AsyncIterator[tuple[PickedMediaItem, SavedInput]]:
    items = await list_google_picker_items(
        http=http,
        access_token=access_token,
        session_id=session_id,
    )
    if len(items) > MAX_IMPORT_ITEMS:
        raise OverflowError("Too many files")

    total = 0
    for index, item in enumerate(items):
        saved = await download_google_item_to_saved(
            http=http,
            access_token=access_token,
            item=item,
            temp_dir=temp_dir,
            index=index,
        )
        total += saved.size
        if total > MAX_VIDEO_BYTES:
            raise OverflowError("Import is too large")
        yield item, saved


async def list_google_picker_items(
    *,
    http: HttpClients,
    access_token: str,
    session_id: PickerSessionId,
) -> list[PickedMediaItem]:
    return await get_media_items(http.gphotos_picker, session_id, access_token)


async def download_google_item_to_saved(
    *,
    http: HttpClients,
    access_token: str,
    item: PickedMediaItem,
    temp_dir: Path,
    index: int = 0,
) -> SavedInput:
    path = temp_dir / f"google-{index}"
    max_bytes = MAX_VIDEO_BYTES if item.type == "VIDEO" else MAX_PHOTO_BYTES
    param = "=dv" if item.type == "VIDEO" else "=d"
    await download_media_to_file(
        http.gphotos_picker,
        item.media_file.base_url,
        access_token,
        path,
        max_bytes=max_bytes,
        param=param,
    )
    return SavedInput(path=path, size=path.stat().st_size)
