from __future__ import annotations

import asyncio
import secrets
import shutil
import tempfile
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from app.core.config import get_settings
from app.models.processing import ArtifactToken

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

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
    ) -> None:
        self._dir_name = dir_name
        self._ttl = ttl
        self._label = label
        self._on_evict = on_evict

    @property
    def _dir(self) -> Path:
        return get_settings().DATA_FOLDER / "tokens" / self._dir_name

    @property
    def _files_dir(self) -> Path:
        return self._dir / "files"

    def cleanup(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        self._files_dir.mkdir(parents=True, exist_ok=True)
        yield

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
        row = await session.get(ArtifactToken, token)
        if row is None or row.namespace != self._dir_name:
            return None
        await session.delete(row)
        data = row.payload
        if _aware(row.expires_at) <= _now():
            await session.commit()
            self._evict(data)
            return None
        await session.commit()
        return data

    def _evict(self, data: dict[str, str]) -> None:
        if self._on_evict is not None:
            self._on_evict(data)
        logger.debug("token.expired", token_label=self._label)
