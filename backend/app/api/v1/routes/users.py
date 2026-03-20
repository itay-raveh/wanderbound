import asyncio
import logging
import shutil
from collections.abc import AsyncIterable
from zipfile import BadZipFile

from fastapi import (
    APIRouter,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.sse import EventSourceResponse
from safezip import SafezipError

from app.core.config import USER_COOKIE
from app.logic.processing import ProcessingEvent
from app.logic.session import process_stream
from app.logic.upload import UserCreated, user_from_zip
from app.models.user import User, UserUpdate

from ..deps import SessionDep, UserDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.post("")
async def create_user(file: UploadFile, response: Response) -> UserCreated:
    logger.info(
        "Extracting '%s' (%d MB)",
        file.filename,
        (file.size or 0) // 1_048_576,
    )
    try:
        result = await user_from_zip(file.file)
    except (BadZipFile, SafezipError, OSError) as e:
        logger.warning("Bad ZIP upload '%s': %s", file.filename, e)
        raise HTTPException(
            status.HTTP_406_NOT_ACCEPTABLE,
            detail="Bad ZIP",
        ) from e
    response.set_cookie(USER_COOKIE, str(result.user.id), httponly=True, samesite="lax")
    return result


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
    await session.refresh(user)
    return user


@router.delete("")
async def delete_user(user: UserDep, session: SessionDep, response: Response) -> None:
    folder = user.folder
    await session.delete(user)
    await session.commit()
    await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)
    response.delete_cookie(USER_COOKIE)
    logger.info("User %d deleted", user.id)
