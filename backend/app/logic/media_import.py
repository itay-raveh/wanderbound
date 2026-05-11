from __future__ import annotations

import tempfile
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

import anyio
import pillow_heif  # noqa: F401 - registers HEIC plugin for Pillow
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.core.resources import MiB
from app.core.worker_threads import run_sync
from app.logic.layout.media import Media, MediaName, extract_frame, media_limiter
from app.logic.media_upgrade.processing import process_photo_sync, process_video
from app.models.album import Album
from app.models.step import Step

if TYPE_CHECKING:
    from fastapi import UploadFile
    from sqlmodel.ext.asyncio.session import AsyncSession

ImportContext = Literal["step", "cover"]

MAX_IMPORT_ITEMS = 50
MAX_PHOTO_BYTES = 200 * MiB
MAX_VIDEO_BYTES = 2 * 1024 * MiB
MAX_BATCH_BYTES = MAX_VIDEO_BYTES
_READ_SIZE = 1024 * 1024


class ImportRequest(BaseModel):
    context: ImportContext
    step_id: int | None = None


class ImportInProgress(BaseModel):
    type: Literal["import_in_progress"] = "import_in_progress"
    phase: str
    done: int
    total: int


class ImportCompleted(BaseModel):
    type: Literal["import_completed"] = "import_completed"
    names: list[MediaName]


class ImportFailed(BaseModel):
    type: Literal["import_failed"] = "import_failed"
    detail: str


ImportEvent = Annotated[
    ImportInProgress | ImportCompleted | ImportFailed,
    Field(discriminator="type"),
]


@dataclass
class SavedInput:
    path: Path
    size: int


def _generated_name(suffix: Literal[".jpg", ".mp4"]) -> MediaName:
    return f"{uuid.uuid4()}_{uuid.uuid4()}{suffix}"


async def save_uploads(files: list[UploadFile], temp_dir: Path) -> list[SavedInput]:
    if not files:
        raise ValueError("No files selected")
    if len(files) > MAX_IMPORT_ITEMS:
        raise OverflowError("Too many files")

    saved: list[SavedInput] = []
    total = 0
    for index, file in enumerate(files):
        path = temp_dir / f"input-{index}"
        size = 0
        async with await anyio.open_file(path, "wb") as out:
            while chunk := await file.read(_READ_SIZE):
                size += len(chunk)
                total += len(chunk)
                if size > MAX_VIDEO_BYTES or total > MAX_BATCH_BYTES:
                    raise OverflowError("Import is too large")
                await out.write(chunk)
        saved.append(SavedInput(path=path, size=size))
    return saved


def _process_photo(raw: Path, output: Path) -> tuple[int, int]:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        return process_photo_sync(raw, output)


async def _import_one(raw: SavedInput, album_dir: Path) -> tuple[Media, Path]:
    name = _generated_name(".jpg")
    output = album_dir / name
    try:
        width, height = await run_sync(
            _process_photo, raw.path, output, limiter=media_limiter
        )
        if raw.size > MAX_PHOTO_BYTES:
            output.unlink(missing_ok=True)
            raise OverflowError("Photo exceeds maximum size")
        return Media(name=name, width=width, height=height), output
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
    ):
        output.unlink(missing_ok=True)

    name = _generated_name(".mp4")
    output = album_dir / name
    try:
        await process_video(raw.path, output)
        media = await Media.probe(output)
        await extract_frame(output)
        media.name = name
    except RuntimeError, OSError, ValueError:
        output.unlink(missing_ok=True)
        output.with_suffix(".jpg").unlink(missing_ok=True)
        raise ValueError("Unsupported or corrupt media") from None
    else:
        return media, output


async def import_saved_media(
    session: AsyncSession,
    *,
    album: Album,
    album_dir: Path,
    request: ImportRequest,
    saved: list[SavedInput],
) -> list[MediaName]:
    if request.context == "step" and request.step_id is None:
        raise ValueError("step_id is required for step imports")

    written: list[Path] = []
    try:
        imported, written = await process_saved_media(
            album_dir=album_dir,
            saved=saved,
        )
        return await persist_imported_media(
            session,
            album=album,
            request=request,
            imported=imported,
        )
    except Exception:
        await cleanup_imported_paths(written)
        raise


async def process_saved_media(
    *,
    album_dir: Path,
    saved: list[SavedInput],
) -> tuple[list[Media], list[Path]]:
    imported: list[Media] = []
    written: list[Path] = []
    try:
        for item in saved:
            media, path = await _import_one(item, album_dir)
            imported.append(media)
            written.append(path)
    except Exception:
        await cleanup_imported_paths(written)
        raise
    return imported, written


async def persist_imported_media(
    session: AsyncSession,
    *,
    album: Album,
    request: ImportRequest,
    imported: list[Media],
) -> list[MediaName]:
    if request.context == "step" and request.step_id is None:
        raise ValueError("step_id is required for step imports")

    names = [m.name for m in imported]
    album.media = [*album.media, *imported]
    session.add(album)

    if request.context == "step":
        step = await session.get_one(Step, (album.uid, album.id, request.step_id))
        step.unused = [*names, *step.unused]
        session.add(step)

    await session.commit()
    return names


async def cleanup_imported_paths(written: list[Path]) -> None:
    for path in written:
        await run_sync(path.unlink, missing_ok=True)
        if path.suffix == ".mp4":
            await run_sync(path.with_suffix(".jpg").unlink, missing_ok=True)


async def import_upload_files(
    session: AsyncSession,
    *,
    album: Album,
    album_dir: Path,
    request: ImportRequest,
    files: list[UploadFile],
) -> list[MediaName]:
    await run_sync(album_dir.mkdir, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=album_dir, prefix=".import-") as tmp:
        temp_dir = Path(tmp)
        saved = await save_uploads(files, temp_dir)
        return await import_saved_media(
            session,
            album=album,
            album_dir=album_dir,
            request=request,
            saved=saved,
        )
