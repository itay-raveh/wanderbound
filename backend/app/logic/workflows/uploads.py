import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

import sentry_sdk
import structlog
from dbos import DBOS, SetWorkflowID
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.logic.eviction import run_eviction
from app.logic.upload import _safe_extract, scan_user_folder
from app.logic.uploads.files import remove_tree_if_present
from app.logic.uploads.finalize import finalize_upload_session
from app.logic.uploads.progress import (
    UploadCompleteEvent,
    UploadErrorEvent,
    UploadPhaseEvent,
    UploadWorkflowEvent,
)
from app.logic.workflows.processing import processing_upload_workflow
from app.models.processing import UploadSession
from app.services.upload_store import UploadStoreService

logger = structlog.get_logger(__name__)


class UploadWorkflowCancelledError(RuntimeError):
    pass


class InvalidUploadArchiveError(ValueError):
    pass


def upload_workflow_id(upload_id: str) -> str:
    return f"upload:{upload_id}"


def _store() -> UploadStoreService:
    from app.main import app  # noqa: PLC0415

    return app.state.upload_store


async def _current_upload(session: AsyncSession, upload_id: str) -> UploadSession:
    row = await session.get(UploadSession, upload_id)
    if row is None or row.status != "processing":
        raise UploadWorkflowCancelledError(upload_id)
    return row


def download_verified_object(
    store: UploadStoreService, object_key: str, destination: Path, expected_size: int
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size == expected_size:
        return destination
    partial = destination.with_suffix(".part")
    partial.unlink(missing_ok=True)
    try:
        with partial.open("wb") as target:
            written = store.download(object_key, target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    if written != expected_size or partial.stat().st_size != expected_size:
        partial.unlink()
        raise OSError("downloaded upload size mismatch")
    partial.replace(destination)
    return destination


def _extract_archive(source: Path, destination: Path) -> None:
    remove_tree_if_present(destination)
    try:
        destination.mkdir(parents=True)
        with source.open("rb") as archive:
            _safe_extract(archive, destination)
        scan_user_folder(destination)
    except (
        BadZipFile,
        ValidationError,
        FileNotFoundError,
        KeyError,
        ValueError,
    ) as exc:
        remove_tree_if_present(destination)
        raise InvalidUploadArchiveError from exc


@DBOS.step(retries_allowed=True, max_attempts=3)
async def download_upload(upload_id: str) -> str:
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        row = await _current_upload(session, upload_id)
        row.updated_at = datetime.now(UTC)
        session.add(row)
        await session.commit()
        destination = (
            get_settings().DATA_FOLDER / "upload-work" / upload_id / "source.zip"
        )
        path = await asyncio.to_thread(
            download_verified_object,
            _store(),
            row.object_key,
            destination,
            row.size_bytes,
        )
    return str(path)


@DBOS.step()
async def extract_upload(upload_id: str, source_path: str) -> str:
    async with AsyncSession(get_engine()) as session:
        row = await _current_upload(session, upload_id)
        row.updated_at = datetime.now(UTC)
        session.add(row)
        await session.commit()
    destination = Path(source_path).parent / "extracted"
    await asyncio.to_thread(_extract_archive, Path(source_path), destination)
    return str(destination)


@DBOS.step(retries_allowed=True, max_attempts=3)
async def finalize_upload(upload_id: str, extracted_path: str) -> dict[str, Any]:
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        row = await _current_upload(session, upload_id)
        row.updated_at = datetime.now(UTC)
        session.add(row)
        await session.commit()
        result, operation, user = await finalize_upload_session(
            session, row, Path(extracted_path)
        )
    return {
        "operation_id": operation.operation_id,
        "uid": user.id,
        "upload_generation": operation.upload_generation,
        "trips_folder": str(user.trips_folder),
        "album_ids": list(result.user.album_ids),
    }


@DBOS.step(retries_allowed=True, max_attempts=3)
async def complete_upload(upload_id: str) -> int:
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        row = await _current_upload(session, upload_id)
        if row.result is None:
            raise UploadWorkflowCancelledError(upload_id)
        await asyncio.to_thread(_store().delete, row.object_key)
        await asyncio.to_thread(
            remove_tree_if_present,
            get_settings().DATA_FOLDER / "upload-work" / upload_id,
        )
        row.status = "succeeded"
        row.completed_at = datetime.now(UTC)
        row.updated_at = row.completed_at
        session.add(row)
        await session.commit()
        return row.result.user.id


@DBOS.step()
async def mark_upload_failed(upload_id: str, error_code: str) -> None:
    async with AsyncSession(get_engine()) as session:
        row = await session.get(UploadSession, upload_id)
        if row is None or row.status != "processing":
            return
        object_key = row.object_key
        row.status = "failed"
        row.error_code = error_code
        row.completed_at = datetime.now(UTC)
        row.updated_at = row.completed_at
        session.add(row)
        await session.commit()
    if error_code == "upload_invalid_zip":
        await asyncio.to_thread(_store().delete, object_key)
        await asyncio.to_thread(
            remove_tree_if_present,
            get_settings().DATA_FOLDER / "upload-work" / upload_id,
        )


@DBOS.step(retries_allowed=True, max_attempts=3)
async def evict_after_upload(uid: int) -> None:
    await run_eviction(uid)


async def _emit_progress(sequence: int, event: UploadWorkflowEvent) -> int:
    await DBOS.set_event_async(str(sequence), event.model_dump(mode="json"))
    return sequence + 1


@DBOS.workflow(name="upload.import")
async def upload_import_workflow(upload_id: str) -> None:
    sequence = await _emit_progress(0, UploadPhaseEvent(phase="downloading"))
    try:
        source = await download_upload(upload_id)
        sequence = await _emit_progress(sequence, UploadPhaseEvent(phase="validating"))
        extracted = await extract_upload(upload_id, source)
        sequence = await _emit_progress(sequence, UploadPhaseEvent(phase="importing"))
        processing = await finalize_upload(upload_id, extracted)
        operation_id = str(processing["operation_id"])
        with SetWorkflowID(f"processing:{operation_id}"):
            await DBOS.start_workflow_async(processing_upload_workflow, processing)
        uid = await complete_upload(upload_id)
        await evict_after_upload(uid)
        await _emit_progress(sequence, UploadCompleteEvent())
    except UploadWorkflowCancelledError:
        return
    except InvalidUploadArchiveError:
        await mark_upload_failed(upload_id, "upload_invalid_zip")
        await _emit_progress(
            sequence, UploadErrorEvent(error_code="upload_invalid_zip")
        )
    except Exception as exc:
        logger.exception("upload.import_failed", upload_id=upload_id)
        sentry_sdk.capture_exception(exc)
        await mark_upload_failed(upload_id, "upload_processing_failed")
        await _emit_progress(
            sequence, UploadErrorEvent(error_code="upload_processing_failed")
        )


async def start_upload_workflow(upload_id: str) -> object:
    with SetWorkflowID(upload_workflow_id(upload_id)):
        return await DBOS.start_workflow_async(upload_import_workflow, upload_id)
