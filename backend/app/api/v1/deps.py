import logging
import time
from collections import OrderedDict
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import sentry_sdk
from fastapi import BackgroundTasks, Depends, HTTPException, Request, status
from playwright.async_api import Browser
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.core.http_clients import HttpClients
from app.models.user import User

if TYPE_CHECKING:
    from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Debounce activity tracking: only write to DB if >1 hour since last write.
# Bounded to 1024 entries to prevent unbounded memory growth.
_ACTIVITY_DEBOUNCE_SECS = 3600
_ACTIVITY_MAX_ENTRIES = 1024
_last_activity_write: OrderedDict[int, float] = OrderedDict()


async def _get_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


async def _touch_activity(uid: int) -> None:
    """Background update of last_active_at with its own session."""
    try:
        async with AsyncSession(get_engine()) as session:
            await session.exec(
                update(User)
                .where(User.id == uid)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
                .values(last_active_at=datetime.now(UTC))
            )
            await session.commit()
    except SQLAlchemyError, OSError:
        logger.debug("Activity tracking write failed for uid=%s", uid, exc_info=True)


async def _get_user(
    request: Request,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> User:
    uid = request.session.get("uid")
    if uid is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    if (user := await session.get(User, uid)) is None:
        logger.warning("Auth failed: unknown uid=%s, clearing stale session", uid)
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    sentry_sdk.set_user({"id": str(uid)})

    # Self-heal: if the stored refresh-token ciphertext could not be decrypted
    # (e.g. after SECRET_KEY rotation), EncryptedString returns None, but
    # connected_at is still set. Collapse to "disconnected" at a single point.
    if (
        user.google_photos_connected_at is not None
        and user.google_photos_refresh_token is None
    ):
        user.google_photos_connected_at = None
        session.add(user)
        await session.commit()

    # Debounced activity tracking
    now = time.monotonic()
    last = _last_activity_write.get(uid, 0.0)
    if now - last > _ACTIVITY_DEBOUNCE_SECS:
        _last_activity_write[uid] = now
        _last_activity_write.move_to_end(uid)
        if len(_last_activity_write) > _ACTIVITY_MAX_ENTRIES:
            _last_activity_write.popitem(last=False)
        background_tasks.add_task(_touch_activity, uid)

    return user


UserDep = Annotated[User, Depends(_get_user)]


async def apply_update[M: SQLModel](
    session: AsyncSession, obj: M, update: BaseModel, *, refresh: bool = True
) -> M:
    """Apply a partial update, commit, and optionally refresh."""
    obj.sqlmodel_update(update.model_dump(exclude_unset=True))
    session.add(obj)
    await session.commit()
    if refresh:
        await session.refresh(obj)
    return obj


async def _get_browser(request: Request) -> Browser:
    return await request.app.state.browser_manager.get()


BrowserDep = Annotated[Browser, Depends(_get_browser)]


def _get_http_clients(request: Request) -> HttpClients:
    return request.app.state.http


HttpClientsDep = Annotated[HttpClients, Depends(_get_http_clients)]


def album_dir(user: User, aid: str) -> Path:
    """Resolve the album directory, rejecting path traversal in ``aid``."""
    resolved = (user.trips_folder / aid).resolve()
    if not resolved.is_relative_to(user.trips_folder):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return resolved


def login_session(request: Request, uid: int) -> None:
    """Set session to the given user (clear first to prevent fixation)."""
    request.session.clear()
    request.session["uid"] = uid
