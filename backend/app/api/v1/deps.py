import logging
import time
from collections import OrderedDict
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated

import sentry_sdk
from fastapi import BackgroundTasks, Depends, HTTPException, Request, status
from playwright.async_api import Browser
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_engine
from app.models.user import User

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
                .where(User.id == uid)  # type: ignore[arg-type]
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


def _get_browser(request: Request) -> Browser:
    return request.app.state.browser


BrowserDep = Annotated[Browser, Depends(_get_browser)]
