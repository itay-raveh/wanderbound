from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.deps import _get_session
from app.core.config import get_settings
from app.core.db import get_engine
from app.main import app
from app.models.polarsteps import PSLocations, PSTrip

from .factories import TRIPS_DIR

# Modules that import get_engine directly and may call it outside DI
# (background tasks, health checks). Patched so tests never hit PostgreSQL.
_GET_ENGINE_TARGETS = [
    "app.core.db.get_engine",
    "app.api.v1.deps.get_engine",
    "app.api.v1.routes.health.get_engine",
    "app.logic.eviction.get_engine",
    "app.logic.pipeline.get_engine",
]


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine() -> AsyncEngine:
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    # Clear the @cache so no stale PostgreSQL engine leaks into tests.
    get_engine.cache_clear()
    return eng


@pytest.fixture(autouse=True, scope="session")
def _patch_get_engine(engine: AsyncEngine) -> Iterator[None]:
    """Redirect get_engine() everywhere so background tasks use SQLite."""
    with ExitStack() as stack:
        for target in _GET_ENGINE_TARGETS:
            stack.enter_context(patch(target, return_value=engine))
        yield


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        txn = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as sess:
            yield sess
        await txn.rollback()


@pytest_asyncio.fixture
async def client(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(get_settings(), "DATA_FOLDER", tmp_path)
    (tmp_path / "users").mkdir(exist_ok=True)

    async def _override() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[_get_session] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def sa_trip_dir() -> Path:
    trip_dir = TRIPS_DIR / "south-america-2024-2025"
    assert trip_dir.exists(), f"SA test data not found at {trip_dir}"
    return trip_dir


@pytest.fixture(scope="module")
def sa_trip(sa_trip_dir: Path) -> PSTrip:
    return PSTrip.from_trip_dir(sa_trip_dir)


@pytest.fixture(scope="module")
def sa_locations(sa_trip_dir: Path) -> PSLocations:
    return PSLocations.from_trip_dir(sa_trip_dir)
