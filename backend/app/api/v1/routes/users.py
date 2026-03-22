import asyncio
import logging
import os
import shutil
from collections.abc import AsyncIterable
from typing import Annotated, cast
from zipfile import BadZipFile

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.sse import EventSourceResponse

from app.core.config import get_settings
from app.core.resources import MiB
from app.logic.eviction import run_eviction
from app.logic.processing import ProcessingEvent
from app.logic.session import cancel_session, process_stream
from app.logic.upload import UploadResult, extract_and_scan
from app.models.user import GoogleIdentity, User, UserUpdate

from ..deps import SessionDep, UserDep
from .auth import verify_google_credential

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


def _check_upload_size(file: UploadFile) -> int:
    """Defense-in-depth size check (nginx is the primary limit)."""
    # Measure actual bytes on disk, not the Content-Length header (spoofable).
    # Seek to end, read cursor position, then reset.
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    max_bytes = get_settings().VITE_MAX_UPLOAD_GB * 1024 * 1024 * 1024
    if size > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Upload too large"
        )
    return size


async def _resolve_auth(
    uid: int | None,
    credential: str | None,
    session: SessionDep,
    request: Request,
) -> tuple[User | None, GoogleIdentity | None]:
    """Return (existing_user, google_identity) or raise 401."""
    if not uid:
        if not credential:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)
        return None, await verify_google_credential(credential)

    existing = await session.get(User, uid)
    if existing:
        return existing, None

    # Stale session pointing to non-existent user (e.g. fresh DB)
    request.session.clear()
    if not credential:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return None, await verify_google_credential(credential)


@router.post("/upload")
async def upload_data(
    file: UploadFile,
    request: Request,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    credential: Annotated[str | None, Form()] = None,
) -> UploadResult:
    uid: int | None = request.session.get("uid")

    # Auth first — reject unauthorized users before processing the ZIP.
    existing, google = await _resolve_auth(uid, credential, session, request)

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
            existing.last_name = existing.last_name or ps_user.last_name
            session.add(existing)
            await session.commit()
            user = existing
            logger.info("User %d re-uploaded ZIP", user.id)
        else:
            # New user: google is guaranteed set (uid was absent -> credential verified)
            g = cast("GoogleIdentity", google)
            user = User(
                id=ps_user.id,
                first_name=g.first_name or ps_user.first_name,
                last_name=g.last_name or ps_user.last_name,
                locale=ps_user.locale,
                unit_is_km=ps_user.unit_is_km,
                temperature_is_celsius=ps_user.temperature_is_celsius,
                google_sub=g.sub,
                profile_image_url=(str(g.picture) if g.picture else None),
                living_location=ps_user.living_location,
                album_ids=album_ids,
            )
            session.add(user)
            await session.commit()
            request.session.clear()
            request.session["uid"] = user.id
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
    return UploadResult(user=user, trips=trips)


@router.get(
    "/process",
    response_class=EventSourceResponse,
    responses={200: {"model": list[ProcessingEvent]}},
)
async def process_user(user: UserDep) -> AsyncIterable[ProcessingEvent]:
    async for event in process_stream(user):
        yield event


@router.get("")
async def read_user(user: UserDep) -> User:
    return user


@router.patch("")
async def update_user(update: UserUpdate, user: UserDep, session: SessionDep) -> User:
    user.sqlmodel_update(update.model_dump(exclude_unset=True))
    session.add(user)
    await session.commit()
    return user


@router.delete("")
async def delete_user(user: UserDep, session: SessionDep, request: Request) -> None:
    cancel_session(user.id)
    folder = user.folder
    await session.delete(user)
    await session.commit()
    await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)
    request.session.clear()
    logger.info("User %d deleted", user.id)
