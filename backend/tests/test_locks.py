from typing import Self
from unittest.mock import patch

from app.core.locks import try_advisory_lock


class _FakeLock:
    released = False

    async def acquire(self, *, block: bool) -> bool:
        assert block is False
        return True

    async def release(self) -> None:
        self.released = True


class _FakeConnection:
    options: dict[str, object] | None = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execution_options(self, **options: object) -> Self:
        self.options = options
        return self


class _FakeEngine:
    connection = _FakeConnection()

    def connect(self) -> _FakeConnection:
        return self.connection


async def test_advisory_lock_connection_uses_autocommit() -> None:
    engine = _FakeEngine()
    lock = _FakeLock()

    with (
        patch("app.core.locks.get_engine", return_value=engine),
        patch("app.core.locks.create_async_sadlock", return_value=lock),
    ):
        async with try_advisory_lock("dbos-admin") as acquired:
            assert acquired is True

    assert engine.connection.options == {"isolation_level": "AUTOCOMMIT"}
    assert lock.released is True
