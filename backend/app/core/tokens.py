import asyncio
import contextlib
import json
import secrets
import shutil
import tempfile
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from time import time
from typing import Any

import structlog

from app.core.config import get_settings

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


class FileTokenStore:
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

    @property
    def _manifests_dir(self) -> Path:
        return self._dir / "manifests"

    def cleanup(self) -> None:
        self._evict_all()
        shutil.rmtree(self._dir, ignore_errors=True)

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        self._files_dir.mkdir(parents=True, exist_ok=True)
        self._manifests_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._cleanup_expired)
        task = asyncio.create_task(self._cleanup_loop())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await asyncio.to_thread(self._cleanup_expired)

    def make_dest(self, suffix: str) -> Path:
        self._files_dir.mkdir(parents=True, exist_ok=True)
        return self._files_dir / f"{secrets.token_hex(16)}{suffix}"

    def store(self, data: dict[str, str]) -> str:
        self._manifests_dir.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe()
        payload: dict[str, Any] = {
            "data": data,
            "expires_at": time() + self._ttl,
        }
        path = self._manifest_path(token)
        tmp_path = path.with_name(f"{path.name}.{secrets.token_hex(8)}.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, sort_keys=True)
        tmp_path.replace(path)
        return token

    def pop(self, token: str) -> dict[str, str] | None:
        try:
            path = self._manifest_path(token)
            payload = self._read_payload(path)
            path.unlink()
        except OSError, TypeError, ValueError, KeyError:
            return None

        data = {str(k): str(v) for k, v in dict(payload["data"]).items()}
        if float(payload["expires_at"]) <= time():
            self._evict(data)
            return None
        return data

    def _cleanup_expired(self) -> None:
        now = time()
        for path in self._manifests_dir.glob("*.json"):
            with contextlib.suppress(OSError, TypeError, ValueError, KeyError):
                payload = self._read_payload(path)
                if float(payload["expires_at"]) <= now:
                    path.unlink(missing_ok=True)
                    data = {str(k): str(v) for k, v in dict(payload["data"]).items()}
                    self._evict(data)

    def _evict_all(self) -> None:
        for path in self._manifests_dir.glob("*.json"):
            with contextlib.suppress(OSError, TypeError, ValueError, KeyError):
                payload = self._read_payload(path)
                path.unlink(missing_ok=True)
                data = {str(k): str(v) for k, v in dict(payload["data"]).items()}
                self._evict(data)

    def _evict(self, data: dict[str, str]) -> None:
        if self._on_evict is not None:
            self._on_evict(data)
        logger.debug("token.expired", token_label=self._label)

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(min(self._ttl, 60))
            await asyncio.to_thread(self._cleanup_expired)

    def _manifest_path(self, token: str) -> Path:
        if not token or "/" in token or "\\" in token or token.startswith("."):
            raise ValueError("invalid token")
        return self._manifests_dir / f"{token}.json"

    @staticmethod
    def _read_payload(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            raise TypeError("invalid token payload")
        return payload
