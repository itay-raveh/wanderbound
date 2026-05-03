import asyncio
import secrets
import shutil
import tempfile
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import structlog

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
