from typing import TYPE_CHECKING, Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.core.logging import config_logger
from app.models.user import User

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = config_logger(__name__)


async def _get_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSession(engine) as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(_get_session)]

USER_COOKIE = "uid"


async def _get_user(
    session: SessionDep, uid: Annotated[int | None, Cookie()] = None
) -> User:
    if uid is None or (user := await session.get(User, uid)) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    # noinspection PyTypeChecker
    return user


UserDep = Annotated[User, Depends(_get_user)]
