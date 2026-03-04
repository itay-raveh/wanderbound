# ruff: noqa: TC003
from collections.abc import Generator
from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Path, status
from sqlmodel import Session

from app.core.logging import config_logger
from app.models.db import Album, AlbumId, Step, StepIdx, User, engine

logger = config_logger(__name__)


def _get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session


DependsSession = Annotated[Session, Depends(_get_session)]


def _get_user(
    session: DependsSession, uid: Annotated[UUID | None, Cookie()] = None
) -> User:
    if uid is None or (user := session.get(User, uid)) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    # noinspection PyTypeChecker
    return user


DependsUser = Annotated[User, Depends(_get_user)]


def _get_album(
    aid: Annotated[AlbumId, Path()], user: DependsUser, session: DependsSession
) -> Album:
    # noinspection PyTypeChecker
    return session.get_one(Album, (user.id, aid))


DependsAlbum = Annotated[Album, Depends(_get_album)]


async def _get_step(
    sid: StepIdx,
    album: DependsAlbum,
    user: DependsUser,
    session: DependsSession,
) -> Step:
    # noinspection PyTypeChecker
    return session.get_one(Step, (user.id, album.id, sid))


DependsStep = Annotated[Step, Depends(_get_step)]
