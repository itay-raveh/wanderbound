from __future__ import annotations

import asyncio
import secrets
import shutil
import tempfile
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.db import get_engine
from app.models.processing import ArtifactToken

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger(__name__)


class TokenStore[T]:
    def __init__(
        self,
        *,
        dir_name: str,
        ttl: int,
        label: str,
        on_evict: Callable[[T], None] | None = None,
    ) -> None:
        self._dir = Path(tempfile.gettempdir()) / dir_name
        self._ttl = ttl
        self._label = label
        self._on_evict = on_evict
        self._tokens: dict[str, tuple[T, asyncio.TimerHandle]] = {}

    def cleanup(self) -> None:
        for data, handle in self._tokens.values():
            handle.cancel()
            if self._on_evict:
                self._on_evict(data)
        self._tokens.clear()
        shutil.rmtree(self._dir, ignore_errors=True)

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        self.cleanup()
        self._dir.mkdir(parents=True, exist_ok=True)
        try:
            yield
        finally:
            self.cleanup()

    def make_dest(self, suffix: str) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        return self._dir / f"{secrets.token_hex(16)}{suffix}"

    def store(self, data: T) -> str:
        token = secrets.token_urlsafe()
        handle = asyncio.get_running_loop().call_later(self._ttl, self._evict, token)
        self._tokens[token] = (data, handle)
        return token

    def pop(self, token: str) -> T | None:
        entry = self._tokens.pop(token, None)
        if entry is None:
            return None
        data, timer = entry
        timer.cancel()
        return data

    def _evict(self, token: str) -> None:
        entry = self._tokens.pop(token, None)
        if entry is not None:
            data, _ = entry
            if self._on_evict:
                self._on_evict(data)
            logger.debug(
                "token.expired",
                token_label=self._label,
                token_prefix=token[:8],
            )


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class ArtifactTokenStore:
    def __init__(
        self,
        *,
        dir_name: str,
        ttl: int,
        label: str,
        on_evict: Callable[[dict[str, str]], None] | None = None,
        cleanup_interval: float = 60.0,
    ) -> None:
        self._dir_name = dir_name
        self._ttl = ttl
        self._label = label
        self._on_evict = on_evict
        self._cleanup_interval = cleanup_interval

    @property
    def _dir(self) -> Path:
        return get_settings().DATA_FOLDER / "tokens" / self._dir_name

    @property
    def _files_dir(self) -> Path:
        return self._dir / "files"

    def cleanup(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)

    @asynccontextmanager
    async def lifespan(
        self, *, engine: AsyncEngine | None = None
    ) -> AsyncGenerator[None]:
        self._files_dir.mkdir(parents=True, exist_ok=True)
        task = asyncio.create_task(self._cleanup_loop(engine))
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _cleanup_loop(self, engine: AsyncEngine | None) -> None:
        while True:
            await asyncio.sleep(self._cleanup_interval)
            try:
                async with AsyncSession(
                    engine or get_engine(), expire_on_commit=False
                ) as session:
                    await self.cleanup_expired(session)
                    await session.commit()
            except Exception:
                logger.exception("token.cleanup_failed", token_label=self._label)

    def make_dest(self, suffix: str) -> Path:
        self._files_dir.mkdir(parents=True, exist_ok=True)
        return self._files_dir / f"{secrets.token_hex(16)}{suffix}"

    async def store(self, session: AsyncSession, data: dict[str, str]) -> str:
        token = secrets.token_urlsafe()
        row = ArtifactToken(
            token=token,
            namespace=self._dir_name,
            path=data["path"],
            payload=data,
            expires_at=_now() + timedelta(seconds=self._ttl),
        )
        session.add(row)
        await session.commit()
        return token

    async def pop(self, session: AsyncSession, token: str) -> dict[str, str] | None:
        if not token or "/" in token or "\\" in token or token.startswith("."):
            return None
        result = await session.exec(
            delete(ArtifactToken)
            .where(col(ArtifactToken.token) == token)
            .where(col(ArtifactToken.namespace) == self._dir_name)
            .returning(
                col(ArtifactToken.payload),
                col(ArtifactToken.expires_at),
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        data, expires_at = row
        if _aware(expires_at) <= _now():
            await session.commit()
            self._evict(data)
            return None
        await session.commit()
        return data

    async def cleanup_expired(self, session: AsyncSession) -> None:
        rows = (
            await session.exec(
                select(ArtifactToken)
                .where(col(ArtifactToken.namespace) == self._dir_name)
                .where(col(ArtifactToken.expires_at) <= _now())
            )
        ).all()
        for row in rows:
            await session.delete(row)
            self._evict(row.payload)

    def _evict(self, data: dict[str, str]) -> None:
        if self._on_evict is not None:
            self._on_evict(data)
        logger.debug("token.expired", token_label=self._label)
