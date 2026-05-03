import asyncio
import io
import shutil
from collections.abc import AsyncIterable
from functools import cache
from pathlib import Path
from secrets import randbelow
from typing import cast
from zipfile import BadZipFile

import httpx
import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response
from fastapi.sse import EventSourceResponse
from httpx_oauth.oauth2 import RevokeTokenError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from starlette.requests import ClientDisconnect

from app.core.config import get_settings
from app.core.resources import MiB
from app.logic.chunked_upload import upload_store
from app.logic.eviction import run_eviction
from app.logic.export import (
    EXPORT_FILENAME,
    ExportEvent,
    export_user_data,
    pop_export_token,
)
from app.logic.session import cancel_session, process_stream
from app.logic.trip_processing import ProcessingEvent
from app.logic.upload import TripMeta, UploadResult, extract_and_scan, scan_user_folder
from app.models.user import (
    OAuthIdentity,
    PSUser,
    User,
    UserPublic,
    UserUpdate,
)

from ..deps import (
    HttpClientsDep,
    SessionDep,
    UserDep,
    apply_update,
    login_session,
    to_user_public,
    try_load_user,
)
from .auth import clear_pending_signup, get_pending_signup

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


def _check_upload_size(file: UploadFile) -> int:
    """Defense-in-depth size check (nginx is the primary limit)."""
    # Measure actual bytes on disk, not the Content-Length header (spoofable).
    file.file.seek(0, io.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    max_bytes = get_settings().VITE_MAX_UPLOAD_GB * 1024 * MiB
    if size > max_bytes:
        logger.warning(
            "upload.rejected_too_large",
            size_mb=size // MiB,
            max_mb=max_bytes // MiB,
        )
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Upload too large")
    return size


async def _resolve_auth(
    request: Request,
    session: SessionDep,
) -> tuple[User | None, OAuthIdentity | None]:
    """Return (existing_user, pending_signup_identity) or raise 401."""
    if existing := await try_load_user(request, session):
        return existing, None
    identity = get_pending_signup(request)
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return None, identity


def _upload_owner(existing: User | None, identity: OAuthIdentity | None) -> str:
    """Stable identifier for the auth principal behind an upload session."""
    if existing is not None:
        return f"uid:{existing.id}"
    assert identity is not None  # noqa: S101 - _resolve_auth guarantees one is set
    return f"{identity.provider}:{identity.sub}"


async def _finalize_upload(  # noqa: PLR0913
    temp_folder: Path,
    ps_user: PSUser,
    trips: list[TripMeta],
    existing: User | None,
    identity: OAuthIdentity | None,
    session: SessionDep,
    request: Request,
    background_tasks: BackgroundTasks,
) -> UploadResult:
    """Shared logic for creating/updating a user after ZIP extraction."""
    album_ids = [t.id for t in trips]

    try:
        cancel_session(ps_user.id)

        if existing is not None:
            existing.album_ids = album_ids
            existing.living_location = ps_user.living_location
            existing.first_name = existing.first_name or ps_user.first_name
            session.add(existing)
            await session.commit()
            user = existing
            logger.info(
                "upload.completed",
                user_id=user.id,
                album_count=len(album_ids),
                new_user=False,
            )
        else:
            oauth = cast("OAuthIdentity", identity)
            user = User(
                id=ps_user.id,
                first_name=oauth.first_name or ps_user.first_name or "Anonymous",
                locale=ps_user.locale,
                unit_is_km=ps_user.unit_is_km,
                temperature_is_celsius=ps_user.temperature_is_celsius,
                google_sub=oauth.sub if oauth.provider == "google" else None,
                microsoft_sub=oauth.sub if oauth.provider == "microsoft" else None,
                profile_image_url=(str(oauth.picture) if oauth.picture else None),
                living_location=ps_user.living_location,
                album_ids=album_ids,
            )
            session.add(user)
            await session.commit()
            login_session(request, user.id)
            clear_pending_signup(request)
            logger.info(
                "upload.completed",
                user_id=user.id,
                album_count=len(album_ids),
                new_user=True,
            )

        target = user.folder
        if target.exists():
            await asyncio.to_thread(shutil.rmtree, target)
        await asyncio.to_thread(temp_folder.rename, target)
    except Exception:
        await asyncio.to_thread(shutil.rmtree, temp_folder, ignore_errors=True)
        raise

    background_tasks.add_task(run_eviction, user.id)
    return UploadResult(user=await to_user_public(user, session), trips=trips)


@router.post("/upload")
async def upload_data(
    file: UploadFile,
    request: Request,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> UploadResult:
    existing, identity = await _resolve_auth(request, session)

    size = _check_upload_size(file)
    logger.info("upload.extracting", size_mb=size // MiB)
    try:
        temp_folder, ps_user, trips = await asyncio.to_thread(
            extract_and_scan, file.file
        )
    except (BadZipFile, OSError, ValidationError) as e:
        logger.warning("upload.bad_zip", error_type=type(e).__name__)
        raise HTTPException(status.HTTP_406_NOT_ACCEPTABLE, detail="Bad ZIP") from e

    return await _finalize_upload(
        temp_folder,
        ps_user,
        trips,
        existing,
        identity,
        session,
        request,
        background_tasks,
    )


# -- Chunked upload -----------------------------------------------------------


@router.post("/upload/init")
async def init_chunked_upload(
    request: Request,
    session: SessionDep,
) -> dict[str, str]:
    """Start a chunked upload session. Returns an opaque upload_id."""
    existing, identity = await _resolve_auth(request, session)

    max_bytes = get_settings().VITE_MAX_UPLOAD_GB * 1024 * MiB
    owner = _upload_owner(existing, identity)
    upload_id = upload_store.create(max_bytes, owner=owner)
    return {"upload_id": upload_id}


@router.put("/upload/{upload_id}/{chunk_index}")
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    request: Request,
) -> Response:
    """Stream a chunk body to disk without loading it into memory.

    No per-request auth: the cryptographic upload_id (256-bit
    ``secrets.token_urlsafe``) acts as a bearer token.  Ownership is
    verified when the session is finalized in ``complete_chunked_upload``.
    """
    try:
        await upload_store.write_chunk_stream(upload_id, chunk_index, request.stream())
    except ClientDisconnect:
        logger.info(
            "upload.chunk_client_disconnected",
            chunk_index=chunk_index,
            upload_id_prefix=upload_id[:8],
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except KeyError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Upload session not found"
        ) from None
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    except OverflowError:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, "Upload too large"
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/upload/{upload_id}/complete")
async def complete_chunked_upload(
    upload_id: str,
    request: Request,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> UploadResult:
    """Assemble chunks and process the ZIP."""
    existing, identity = await _resolve_auth(request, session)

    owner = _upload_owner(existing, identity)
    try:
        assembled, upload_dir = await asyncio.to_thread(
            upload_store.assemble, upload_id, owner=owner
        )
    except KeyError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Upload session not found"
        ) from None
    except PermissionError:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Upload session belongs to a different user"
        ) from None
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None

    try:
        temp_folder, ps_user, trips = await asyncio.to_thread(
            extract_and_scan, assembled
        )
    except (BadZipFile, OSError, ValidationError) as e:
        logger.warning(
            "upload.bad_zip",
            error_type=type(e).__name__,
        )
        raise HTTPException(status.HTTP_406_NOT_ACCEPTABLE, detail="Bad ZIP") from e
    finally:
        assembled.close()
        await asyncio.to_thread(shutil.rmtree, upload_dir, ignore_errors=True)

    return await _finalize_upload(
        temp_folder,
        ps_user,
        trips,
        existing,
        identity,
        session,
        request,
        background_tasks,
    )


@cache
def _demo_fixtures() -> tuple[Path, PSUser, tuple[TripMeta, ...]]:
    """Cached - callers must not mutate the returned objects."""
    fixtures = get_settings().DEMO_FIXTURES
    ps_user, trips = scan_user_folder(fixtures)
    return fixtures, ps_user, tuple(trips)


def _demo_locale(request: Request, fallback: str) -> str:
    """Extract primary language from Accept-Language header.

    Returns the raw tag (e.g. ``en-US``); Pydantic's ``Locale`` validator
    handles normalization and rejects invalid values on model construction.
    """
    accept = request.headers.get("accept-language", "")
    if accept:
        tag = accept.split(",")[0].split(";")[0].strip()
        if 2 <= len(tag) <= 5:
            return tag
    return fallback


@router.post("/demo")
async def create_demo(
    request: Request,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> UploadResult:
    fixtures, ps_user, trips = _demo_fixtures()
    album_ids = [t.id for t in trips]

    def _link_or_copy(src: str, dst: str) -> None:
        try:
            Path(dst).hardlink_to(src)
        except OSError:
            shutil.copy2(src, dst)

    for _ in range(5):
        uid = 2_000_000_000 + randbelow(147_483_648)
        user = User(
            id=uid,
            first_name=ps_user.first_name or "Demo",
            locale=_demo_locale(request, ps_user.locale),
            unit_is_km=ps_user.unit_is_km,
            temperature_is_celsius=ps_user.temperature_is_celsius,
            living_location=ps_user.living_location,
            album_ids=album_ids,
            is_demo=True,
        )

        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            continue

        try:
            await asyncio.to_thread(
                shutil.copytree,
                fixtures,
                user.folder,
                ignore=shutil.ignore_patterns("i18n"),
                copy_function=_link_or_copy,
            )
        except OSError:
            logger.exception("demo.copy_failed", user_id=uid)
            await session.delete(user)
            await session.commit()
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None
        break
    else:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE)

    login_session(request, user.id)

    background_tasks.add_task(run_eviction, user.id)
    return UploadResult(user=await to_user_public(user, session), trips=list(trips))


async def _remove_user(
    user: User, session: SessionDep, request: Request, http: HttpClientsDep
) -> None:
    cancel_session(user.id)
    folder = user.folder
    if user.google_photos_refresh_token:
        try:
            await http.gphotos_oauth.revoke_token(user.google_photos_refresh_token)
        except (RevokeTokenError, httpx.HTTPError) as exc:
            logger.warning("oauth.token_revoke_failed", error_type=type(exc).__name__)
    await session.delete(user)
    await session.commit()
    await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)
    request.session.clear()
    logger.info("user.deleted", user_id=user.id, is_demo=user.is_demo)


@router.delete("/demo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_demo(
    user: UserDep,
    session: SessionDep,
    request: Request,
    http: HttpClientsDep,
) -> None:
    if not user.is_demo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not a demo user")
    await _remove_user(user, session, request, http)


@router.get(
    "/process",
    response_class=EventSourceResponse,
    responses={200: {"model": list[ProcessingEvent]}},
)
async def process_user(
    user: UserDep, http: HttpClientsDep
) -> AsyncIterable[ProcessingEvent]:
    async for event in process_stream(http, user):
        yield event


@router.get(
    "/export",
    response_class=EventSourceResponse,
    responses={200: {"model": list[ExportEvent]}},
)
async def export_data(user: UserDep, session: SessionDep) -> AsyncIterable[ExportEvent]:
    async for event in export_user_data(user, session):
        yield event


@router.get("/export/download/{token}")
async def download_export(
    token: str, background_tasks: BackgroundTasks
) -> FileResponse:
    result = pop_export_token(token)
    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Invalid or expired token"
        )
    background_tasks.add_task(result.unlink, missing_ok=True)
    return FileResponse(
        result,
        media_type="application/zip",
        filename=EXPORT_FILENAME,
    )


@router.get("")
async def read_user(user: UserDep, session: SessionDep) -> UserPublic:
    return await to_user_public(user, session)


@router.patch("")
async def update_user(
    update: UserUpdate, user: UserDep, session: SessionDep
) -> UserPublic:
    updated = await apply_update(session, user, update, refresh=False)
    return await to_user_public(updated, session)


@router.delete("")
async def delete_user(
    user: UserDep, session: SessionDep, request: Request, http: HttpClientsDep
) -> None:
    await _remove_user(user, session, request, http)
