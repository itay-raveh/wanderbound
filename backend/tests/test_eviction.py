from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.logic import eviction
from app.models.album import Album
from app.models.user import User
from tests.factories import insert_album, make_user

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest_asyncio.fixture
async def storage_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'storage.sqlite'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    monkeypatch.setattr(eviction, "get_engine", lambda: engine)
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _seed(
    engine: AsyncEngine, uid: int, albums: list[tuple[str, int]], *, demo: bool = False
) -> None:
    async with AsyncSession(engine) as session:
        session.add(make_user(uid, is_demo=demo, album_ids=[aid for aid, _ in albums]))
        await session.flush()
        for aid, hours in albums:
            album = await insert_album(session, uid, aid)
            album.last_active_at = datetime.now(UTC) - timedelta(hours=hours)
            session.add(album)
            path = get_settings().USERS_FOLDER / str(uid) / "trip" / aid / "data.bin"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"original" * 10)
        await session.commit()


async def test_real_user_eviction_preserves_records_and_uploading_user(
    storage_db: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed(storage_db, 1, [("old", 72), ("recent", 1)])
    await _seed(storage_db, 2, [("uploading", 100)])
    monkeypatch.setattr(get_settings(), "MAX_STORAGE_BYTES", 160)
    await eviction.run_eviction(skip_uid=2)
    users = get_settings().USERS_FOLDER
    assert not (users / "1/trip/old").exists()
    assert (users / "1/trip/recent/data.bin").read_bytes() == b"original" * 10
    assert (users / "2/trip/uploading/data.bin").read_bytes() == b"original" * 10
    async with AsyncSession(storage_db) as session:
        assert await session.get(User, 1) is not None
        assert await session.get(Album, (1, "old")) is not None
        assert await session.get(Album, (1, "recent")) is not None


def _inject_failure(fault: pytest.MonkeyPatch, failure: str) -> None:
    if failure in {"commit", "new-session"}:

        async def broken_commit(self: AsyncSession) -> None:
            raise OSError("commit interrupted")

        fault.setattr(AsyncSession, "commit", broken_commit)
    elif failure == "cleanup":

        def broken_cleanup(path: Path) -> None:
            raise OSError("cleanup interrupted")

        fault.setattr(eviction, "_remove_tree", broken_cleanup)


@pytest.mark.parametrize("failure", ["none", "commit", "cleanup", "new-session"])
async def test_demo_eviction_recovers_without_deleting_other_sessions(
    storage_db: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    await _seed(storage_db, 1, [("old", 72), ("recent", 1)], demo=True)
    await _seed(storage_db, 2, [("real", 24)])
    monkeypatch.setattr(get_settings(), "MAX_STORAGE_BYTES", 100)
    users = get_settings().USERS_FOLDER
    with monkeypatch.context() as fault:
        _inject_failure(fault, failure)
        if failure == "none":
            await eviction.run_eviction(skip_uid=2)
        else:
            with pytest.raises(OSError, match="interrupted"):
                await eviction.run_eviction(skip_uid=2)
    pending = users / ".evictions/1"
    if failure != "none":
        assert (pending / "trip/old/data.bin").read_bytes() == b"original" * 10
        async with AsyncSession(storage_db) as session:
            assert (await session.get(User, 1) is None) == (failure == "cleanup")
        await eviction.run_eviction(skip_uid=1)
        assert pending.exists()
        if failure == "new-session":
            fresh = users / "1/trip/new/data.bin"
            fresh.parent.mkdir(parents=True)
            fresh.write_bytes(b"new session")
            async with AsyncSession(storage_db) as session:
                user = await session.get_one(User, 1)
                user.album_ids = ["new"]
                session.add(user)
                await session.commit()
        await eviction.run_eviction(skip_uid=2)
    assert not pending.exists()
    async with AsyncSession(storage_db) as session:
        assert (await session.get(User, 1) is not None) == (failure == "new-session")
        assert await session.get(User, 2) is not None
    if failure == "new-session":
        assert (users / "1/trip/new/data.bin").read_bytes() == b"new session"
    else:
        assert not (users / "1").exists()
    assert (users / "2/trip/real/data.bin").read_bytes() == b"original" * 10
