import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.locks import try_advisory_lock
from app.logic.session import _operation_for_process_request
from app.models.processing import ProcessingOperation
from tests.factories import make_user


@asynccontextmanager
async def _locked(engine: AsyncEngine, key: str) -> AsyncIterator[bool]:
    with patch("app.core.locks.get_engine", return_value=engine):
        async with try_advisory_lock(key) as acquired:
            yield acquired


@pytest.mark.parametrize("exit_mode", ["normal", "exception", "disconnect"])
async def test_advisory_lock_excludes_competitors_and_recovers(
    postgres_engine: AsyncEngine, exit_mode: str
) -> None:
    peer = create_async_engine(postgres_engine.url)
    key = "test-" + uuid4().hex

    async def held_operation() -> None:
        async with _locked(postgres_engine, key) as acquired:
            assert acquired
            async with _locked(peer, key) as competitor:
                assert not competitor
            if exit_mode == "exception":
                raise ValueError("interrupted operation")
            if exit_mode == "disconnect":
                async with peer.connect() as conn:
                    pid = await conn.scalar(
                        text(
                            "SELECT locks.pid FROM pg_locks locks "
                            "JOIN pg_stat_activity activity USING (pid) "
                            "WHERE locks.locktype = 'advisory' AND locks.granted "
                            "AND activity.application_name = :name"
                        ),
                        {"name": postgres_engine.url.query["application_name"]},
                    )
                    assert pid is not None
                    await conn.execute(
                        text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}
                    )
                async with _locked(peer, key) as recovered:
                    assert recovered

    try:
        if exit_mode == "normal":
            await held_operation()
        else:
            error = ValueError if exit_mode == "exception" else DBAPIError
            with pytest.raises(error):
                await held_operation()
        async with _locked(peer, key) as recovered:
            assert recovered
    finally:
        await peer.dispose()


async def test_concurrent_processing_decisions_reuse_one_durable_operation(
    postgres_engine: AsyncEngine,
) -> None:
    user = make_user(222, google_sub="lock-test")
    async with AsyncSession(postgres_engine, expire_on_commit=False) as seed:
        seed.add(user)
        await seed.commit()

    async with (
        AsyncSession(postgres_engine, expire_on_commit=False) as first,
        AsyncSession(postgres_engine, expire_on_commit=False) as second,
    ):
        operation = await _operation_for_process_request(first, user)
        second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
        contender = asyncio.create_task(_operation_for_process_request(second, user))
        try:
            async with asyncio.timeout(5):
                async with postgres_engine.connect() as observer:
                    while not await observer.scalar(
                        text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"),
                        {"pid": second_pid},
                    ):
                        assert not contender.done(), "processing decision bypassed lock"
                        await asyncio.sleep(0.01)
            await first.commit()
            reused = await contender
            await second.commit()
            assert reused.operation_id == operation.operation_id
        finally:
            contender.cancel()
            await asyncio.gather(contender, return_exceptions=True)

    async with AsyncSession(postgres_engine) as persisted:
        rows = (await persisted.exec(select(ProcessingOperation))).all()
        assert [(row.operation_id, row.uid, row.upload_generation) for row in rows] == [
            (operation.operation_id, user.id, 1)
        ]
