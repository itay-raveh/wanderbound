import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from sqlmodel import col, select

from app.api.v1.deps import to_user_public
from app.core.config import get_settings
from app.logic.processing_operations import mark_user_processing_operations_stale
from app.logic.session import cancel_session
from app.logic.upload import scan_user_folder
from app.logic.uploads.files import remove_tree_if_present
from app.models.processing import ProcessingOperation, UploadSession
from app.models.upload import UploadResult
from app.models.user import PSUser, User

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

_MARKER = ".wanderbound-upload-id"


def finalization_operation_id(upload_id: str) -> str:
    return f"upload:{upload_id}:processing"


def recover_finalization_source(
    expected: Path, users_folder: Path, upload_id: str
) -> Path:
    for candidate in users_folder.iterdir():
        marker = candidate / _MARKER
        if candidate.is_dir() and marker.is_file() and marker.read_text() == upload_id:
            return candidate
    if expected.exists():
        return expected
    raise FileNotFoundError(expected)


def replace_user_folder_once(source: Path, target: Path, *, marker: str) -> None:
    backup = target.with_name(f"{target.name}.upload-backup-{marker}")
    marker_path = target / _MARKER
    if marker_path.is_file() and marker_path.read_text() == marker:
        if source != target:
            remove_tree_if_present(source)
        remove_tree_if_present(backup)
        return
    if not source.exists():
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise FileNotFoundError(source)
    if target.exists():
        remove_tree_if_present(backup)
        target.rename(backup)
    try:
        (source / _MARKER).write_text(marker)
        source.rename(target)
    except Exception:
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise
    remove_tree_if_present(backup)


def _apply_archive_profile(user: User, ps_user: PSUser, album_ids: list[str]) -> None:
    user.album_ids = album_ids
    user.living_location = ps_user.living_location
    user.first_name = user.first_name or ps_user.first_name


async def finalize_upload_session(
    session: AsyncSession, upload: UploadSession, extracted_folder: Path
) -> tuple[UploadResult, ProcessingOperation, User]:
    source = await asyncio.to_thread(
        recover_finalization_source,
        extracted_folder,
        get_settings().USERS_FOLDER,
        upload.upload_id,
    )
    operation_id = finalization_operation_id(upload.upload_id)
    if upload.result is None:
        ps_user, trips = await asyncio.to_thread(scan_user_folder, source)
        album_ids = [trip.id for trip in trips]
        if upload.owner.startswith("uid:"):
            user = await session.get(User, int(upload.owner.removeprefix("uid:")))
            if user is None:
                raise RuntimeError("upload owner no longer exists")
            _apply_archive_profile(user, ps_user, album_ids)
        else:
            provider, sub = upload.owner.split(":", 1)
            provider_column = (
                User.google_sub if provider == "google" else User.microsoft_sub
            )
            user = (
                await session.exec(select(User).where(provider_column == sub))
            ).first()
            if user is None:
                user = User(
                    id=ps_user.id,
                    first_name=ps_user.first_name or "Anonymous",
                    locale=ps_user.locale,
                    unit_is_km=ps_user.unit_is_km,
                    temperature_is_celsius=ps_user.temperature_is_celsius,
                    google_sub=sub if provider == "google" else None,
                    microsoft_sub=sub if provider == "microsoft" else None,
                    living_location=ps_user.living_location,
                    album_ids=album_ids,
                )
            else:
                _apply_archive_profile(user, ps_user, album_ids)
        cancel_session(user.id)
        await mark_user_processing_operations_stale(session, uid=user.id)
        session.add(user)
        await session.flush()
        operation = await session.get(ProcessingOperation, operation_id)
        if operation is None:
            latest_generation = await session.scalar(
                select(ProcessingOperation.upload_generation)
                .where(ProcessingOperation.uid == user.id)
                .order_by(col(ProcessingOperation.upload_generation).desc())
                .limit(1)
            )
            operation = ProcessingOperation(
                operation_id=operation_id,
                uid=user.id,
                upload_generation=(latest_generation or 0) + 1,
                workflow_id=f"processing:{operation_id}",
            )
            session.add(operation)
        public = await to_user_public(user, session)
        public.has_data = True
        result = UploadResult(user=public, trips=trips)
        upload.result = result
        session.add(upload)
        await session.commit()
    else:
        result = upload.result
        user = await session.get(User, result.user.id)
        operation = await session.get(ProcessingOperation, operation_id)
        if user is None or operation is None:
            raise RuntimeError("committed upload finalization is incomplete")
    await asyncio.to_thread(
        replace_user_folder_once, source, user.folder, marker=upload.upload_id
    )
    return result, operation, user
