from pathlib import Path
from typing import TYPE_CHECKING

from app.logic.layout.media import MediaName
from app.logic.media_import import ImportRequest, import_upload_files
from app.models.album import Album

if TYPE_CHECKING:
    from fastapi import UploadFile
    from sqlmodel.ext.asyncio.session import AsyncSession


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
