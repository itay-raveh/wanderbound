# ruff: noqa: TC003
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Path, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import config_logger
from app.models.db import Album, AlbumId, User, engine

logger = config_logger(__name__)


async def _get_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSession(engine) as session:
        yield session


DependsSession = Annotated[AsyncSession, Depends(_get_session)]

USER_COOKIE = "uid"

async def _get_user(session: DependsSession, uid: Annotated[int | None, Cookie()] = None) -> User:
    if uid is None or (user := await session.get(User, uid)) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    # noinspection PyTypeChecker
    return user


DependsUser = Annotated[User, Depends(_get_user)]


async def _get_album(
    aid: Annotated[AlbumId, Path()], user: DependsUser, session: DependsSession
) -> Album:
    # noinspection PyTypeChecker
    return await session.get_one(Album, (user.id, aid))


DependsAlbum = Annotated[Album, Depends(_get_album)]
