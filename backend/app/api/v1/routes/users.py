import asyncio
import io
import logging
import shutil
from collections.abc import AsyncIterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from secrets import randbelow
from typing import Annotated, Any, cast
from zipfile import BadZipFile

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.resources import MiB
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
    AuthProvider,
    OAuthIdentity,
    PSUser,
    User,
    UserPublic,
    UserUpdate,
)

from ..deps import SessionDep, UserDep, apply_update, login_session
from .auth import verify_credential

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@dataclass
class _AuthForm:
    credential: Annotated[str | None, Form()] = None
    provider: Annotated[AuthProvider | None, Form()] = None


def _check_upload_size(file: UploadFile) -> int:
    """Defense-in-depth size check (nginx is the primary limit)."""
    # Measure actual bytes on disk, not the Content-Length header (spoofable).
    file.file.seek(0, io.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    max_bytes = get_settings().VITE_MAX_UPLOAD_GB * 1024 * MiB
    if size > max_bytes:
        logger.warning(
            "Upload rejected: %d MB exceeds %d MB limit",
            size // MiB,
            max_bytes // MiB,
        )
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Upload too large"
        )
    return size


async def _resolve_auth(
    uid: int | None,
    credential: str | None,
    provider: AuthProvider | None,
    session: SessionDep,
    request: Request,
) -> tuple[User | None, OAuthIdentity | None]:
    """Return (existing_user, oauth_identity) or raise 401."""
    if uid:
        existing = await session.get(User, uid)
        if existing:
            return existing, None
        # Stale session pointing to non-existent user (e.g. fresh DB)
        request.session.clear()

    if not credential or not provider:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return None, await verify_credential(credential, provider)


@router.post("/upload")
async def upload_data(
    file: UploadFile,
    request: Request,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    auth: Annotated[_AuthForm, Depends()],
) -> UploadResult:
    uid: int | None = request.session.get("uid")

    # Auth first - reject unauthorized users before processing the ZIP.
    existing, identity = await _resolve_auth(
        uid, auth.credential, auth.provider, session, request
    )

    size = _check_upload_size(file)
    logger.info("Extracting '%s' (%d MB)", file.filename, size // MiB)
    try:
        temp_folder, ps_user, trips = await asyncio.to_thread(
            extract_and_scan, file.file
        )
    except (BadZipFile, OSError) as e:
        logger.warning("Bad ZIP upload '%s': %s", file.filename, e)
        raise HTTPException(
            status.HTTP_406_NOT_ACCEPTABLE,
            detail="Bad ZIP",
        ) from e

    album_ids = [t.id for t in trips]

    cancel_session(ps_user.id)

    try:
        if existing is not None:
            # Re-upload: update existing user with new ZIP data
            existing.album_ids = album_ids
            existing.living_location = ps_user.living_location
            existing.first_name = existing.first_name or ps_user.first_name
            session.add(existing)
            await session.commit()
            user = existing
            logger.info("User %d re-uploaded ZIP", user.id)
        else:
            # New user: identity is guaranteed set (uid was absent)
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
            logger.info("New user %d created via upload", user.id)

        # Move extracted data to user's permanent folder
        target = user.folder
        if target.exists():
            await asyncio.to_thread(shutil.rmtree, target)
        await asyncio.to_thread(temp_folder.rename, target)
    except Exception:
        await asyncio.to_thread(shutil.rmtree, temp_folder, ignore_errors=True)
        raise

    background_tasks.add_task(run_eviction, user.id)
    return UploadResult(user=UserPublic.model_validate(user), trips=trips)


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
            logger.exception("Demo copytree failed for user %d", uid)
            await session.delete(user)
            await session.commit()
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None
        break
    else:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE)

    login_session(request, user.id)

    background_tasks.add_task(run_eviction, user.id)
    return UploadResult(user=UserPublic.model_validate(user), trips=list(trips))


async def _remove_user(user: User, session: SessionDep, request: Request) -> None:
    cancel_session(user.id)
    folder = user.folder
    await session.delete(user)
    await session.commit()
    await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)
    request.session.clear()
    logger.info("User %d deleted", user.id)


@router.delete("/demo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_demo(
    user: UserDep,
    session: SessionDep,
    request: Request,
) -> None:
    if not user.is_demo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not a demo user")
    await _remove_user(user, session, request)


@router.get(
    "/process",
    response_class=EventSourceResponse,
    responses={200: {"model": list[ProcessingEvent]}},
)
async def process_user(user: UserDep) -> AsyncIterable[ProcessingEvent]:
    async for event in process_stream(user):
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


@router.get("", response_model=UserPublic)
async def read_user(user: UserDep) -> Any:
    return user


@router.patch("", response_model=UserPublic)
async def update_user(update: UserUpdate, user: UserDep, session: SessionDep) -> Any:
    return await apply_update(session, user, update, refresh=False)


@router.delete("")
async def delete_user(user: UserDep, session: SessionDep, request: Request) -> None:
    await _remove_user(user, session, request)
