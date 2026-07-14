import asyncio
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.deps import SessionDep, UploadStoreDep, login_session
from app.core.config import get_settings
from app.logic.workflows.uploads import start_upload_workflow
from app.models.processing import UPLOAD_PART_SIZE_BYTES, UploadSession, UploadStatus
from app.models.upload import UploadResult
from app.models.user import User
from app.services.upload_store import CompletionPart, ProviderPart, UploadStoreError

from .auth import clear_pending_signup, get_pending_signup
from .users import _resolve_auth, _upload_owner

router = APIRouter(prefix="/users/uploads", tags=["users"])


class UploadHTTPException(HTTPException):
    pass


class UploadMetadata(BaseModel):
    size_bytes: int


class CreateUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    type: str = Field(min_length=1, max_length=255)
    metadata: UploadMetadata


class CreateUploadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    upload_id: str = Field(serialization_alias="uploadId")
    key: str


class SignPartResponse(BaseModel):
    method: Literal["PUT"] = "PUT"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class CompletePart(BaseModel):
    PartNumber: int = Field(ge=1, le=64)
    ETag: str = Field(min_length=1, max_length=128)


class CompleteUploadRequest(BaseModel):
    parts: list[CompletePart] = Field(min_length=1, max_length=64)


class CompleteUploadResponse(BaseModel):
    location: str


class UploadStatusResponse(BaseModel):
    status: UploadStatus
    error_code: str | None
    result: UploadResult | None


def _error(code: str, http_status: int) -> UploadHTTPException:
    return UploadHTTPException(http_status, code)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _owned_upload(
    request: Request, session: SessionDep, upload_id: str
) -> UploadSession:
    existing, identity = await _resolve_auth(request, session)
    owner = _upload_owner(existing, identity)
    row = await session.get(UploadSession, upload_id)
    if row is None or row.owner != owner:
        raise _error("upload_not_found", status.HTTP_404_NOT_FOUND)
    return row


def _require_key(row: UploadSession, key: str) -> None:
    if key != row.object_key:
        raise _error("upload_not_found", status.HTTP_404_NOT_FOUND)


def _part_size(row: UploadSession, part_number: int) -> int:
    count = (row.size_bytes + UPLOAD_PART_SIZE_BYTES - 1) // UPLOAD_PART_SIZE_BYTES
    if not 1 <= part_number <= count:
        raise _error("upload_invalid_part", status.HTTP_422_UNPROCESSABLE_CONTENT)
    return min(
        UPLOAD_PART_SIZE_BYTES,
        row.size_bytes - (part_number - 1) * UPLOAD_PART_SIZE_BYTES,
    )


def _ensure_uploading(row: UploadSession) -> None:
    if _aware(row.expires_at) <= datetime.now(UTC):
        raise _error("upload_expired", status.HTTP_410_GONE)
    if row.status != "uploading":
        raise _error("upload_not_active", status.HTTP_409_CONFLICT)


@router.post("/s3/multipart", status_code=status.HTTP_201_CREATED)
async def create_upload(
    payload: CreateUploadRequest,
    request: Request,
    session: SessionDep,
    store: UploadStoreDep,
) -> CreateUploadResponse:
    maximum = get_settings().VITE_MAX_UPLOAD_GB * 1024**3
    if not 0 < payload.metadata.size_bytes <= maximum:
        raise _error("upload_invalid_size", status.HTTP_400_BAD_REQUEST)
    existing, identity = await _resolve_auth(request, session)
    row = UploadSession.new(
        owner=_upload_owner(existing, identity),
        provider_upload_id="pending",
        filename=payload.filename,
        content_type=payload.type,
        size_bytes=payload.metadata.size_bytes,
        ttl_seconds=get_settings().UPLOAD_SESSION_TTL_SECONDS,
    )
    try:
        row.provider_upload_id = await asyncio.to_thread(
            store.create, row.object_key, row.content_type
        )
    except UploadStoreError:
        raise _error(
            "upload_store_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE
        ) from None
    session.add(row)
    await session.commit()
    return CreateUploadResponse(upload_id=row.upload_id, key=row.object_key)


@router.get("/s3/multipart/{upload_id}/{part_number}")
async def sign_part(  # noqa: PLR0913
    upload_id: str,
    part_number: int,
    key: str,
    request: Request,
    session: SessionDep,
    store: UploadStoreDep,
) -> SignPartResponse:
    row = await _owned_upload(request, session, upload_id)
    _require_key(row, key)
    _ensure_uploading(row)
    try:
        url = await asyncio.to_thread(
            store.sign_part,
            row.object_key,
            row.provider_upload_id,
            part_number,
            _part_size(row, part_number),
        )
    except UploadStoreError:
        raise _error(
            "upload_store_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE
        ) from None
    return SignPartResponse(url=url)


@router.get("/s3/multipart/{upload_id}")
async def list_parts(
    upload_id: str,
    key: str,
    request: Request,
    session: SessionDep,
    store: UploadStoreDep,
) -> list[ProviderPart]:
    row = await _owned_upload(request, session, upload_id)
    _require_key(row, key)
    _ensure_uploading(row)
    try:
        return await asyncio.to_thread(
            store.list_parts, row.object_key, row.provider_upload_id
        )
    except UploadStoreError:
        raise _error(
            "upload_store_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE
        ) from None


@router.post("/s3/multipart/{upload_id}/complete")
async def complete_upload(  # noqa: PLR0913
    upload_id: str,
    key: str,
    payload: CompleteUploadRequest,
    request: Request,
    session: SessionDep,
    store: UploadStoreDep,
) -> CompleteUploadResponse:
    row = await _owned_upload(request, session, upload_id)
    _require_key(row, key)
    if row.status == "processing":
        await start_upload_workflow(row.upload_id)
        return CompleteUploadResponse(location=row.object_key)
    _ensure_uploading(row)
    parts = [CompletionPart(**part.model_dump()) for part in payload.parts]
    try:
        await asyncio.to_thread(
            store.complete, row.object_key, row.provider_upload_id, parts
        )
        size = await asyncio.to_thread(store.head, row.object_key)
    except UploadStoreError:
        raise _error(
            "upload_store_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE
        ) from None
    if size != row.size_bytes:
        await asyncio.to_thread(store.delete, row.object_key)
        raise _error("upload_size_mismatch", status.HTTP_409_CONFLICT)
    row.status = "processing"
    row.updated_at = datetime.now(UTC)
    session.add(row)
    await session.commit()
    await start_upload_workflow(row.upload_id)
    return CompleteUploadResponse(location=row.object_key)


@router.delete("/s3/multipart/{upload_id}")
async def abort_upload(
    upload_id: str,
    key: str,
    request: Request,
    session: SessionDep,
    store: UploadStoreDep,
) -> dict[str, object]:
    row = await _owned_upload(request, session, upload_id)
    _require_key(row, key)
    _ensure_uploading(row)
    try:
        await asyncio.to_thread(store.abort, row.object_key, row.provider_upload_id)
    except UploadStoreError:
        raise _error(
            "upload_store_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE
        ) from None
    row.status = "aborted"
    row.completed_at = datetime.now(UTC)
    row.updated_at = row.completed_at
    session.add(row)
    await session.commit()
    return {}


@router.get("/{upload_id}")
async def upload_status(
    upload_id: str, request: Request, session: SessionDep
) -> UploadStatusResponse:
    row = await _owned_upload(request, session, upload_id)
    pending = get_pending_signup(request)
    if row.status == "succeeded" and row.result is not None and pending is not None:
        user = row.result.user
        db_user = await session.get(User, user.id)
        if db_user is None:
            raise _error("upload_not_found", status.HTTP_404_NOT_FOUND)
        db_user.first_name = pending.first_name or db_user.first_name
        db_user.profile_image_url = str(pending.picture) if pending.picture else None
        row.owner = f"uid:{db_user.id}"
        row.result = row.result.model_copy(
            update={
                "user": user.model_copy(
                    update={
                        "first_name": db_user.first_name,
                        "profile_image_url": db_user.profile_image_url,
                    }
                )
            }
        )
        session.add(db_user)
        session.add(row)
        await session.commit()
        login_session(request, db_user.id)
        clear_pending_signup(request)
    return UploadStatusResponse(
        status=row.status,
        error_code=row.error_code,
        result=row.result,
    )
