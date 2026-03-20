import logging
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from playwright.async_api import Browser
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.models.user import User

logger = logging.getLogger(__name__)


async def _get_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]


async def _get_user(request: Request, session: SessionDep) -> User:
    uid = request.session.get("uid")
    if uid is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    if (user := await session.get(User, uid)) is None:
        logger.warning("Auth failed: unknown uid=%s", uid)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return user


UserDep = Annotated[User, Depends(_get_user)]


def _get_browser(request: Request) -> Browser:
    return request.app.state.browser


BrowserDep = Annotated[Browser, Depends(_get_browser)]
