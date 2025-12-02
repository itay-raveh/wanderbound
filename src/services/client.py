"""Shared utilities for services: API client and helpers."""

from types import TracebackType
from typing import Any

import httpx
from httpx import AsyncClient
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.core.logger import get_logger

logger = get_logger(__name__)


class APIClient:
    """Async API client with caching, rate limiting, and retries."""

    def __init__(self, base_url: str = "") -> None:
        self._client = AsyncClient(base_url=httpx.URL(base_url))

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "APIClient":
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch JSON data with rate limiting and retries."""
        data = await self._fetch(url, params=params, response_type="json")
        return dict(data)

    async def get_content(self, url: str, params: dict[str, Any] | None = None) -> bytes:
        """Fetch binary content with rate limiting and retries."""
        content = await self._fetch(url, params=params, response_type="content")
        return bytes(content)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(
            lambda exc: isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500
        ),
        reraise=True,
    )
    async def _fetch(self, url: str, params: dict[str, Any] | None, response_type: str) -> Any:
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            raise
        else:
            if response_type == "json":
                return response.json()
            return response.content
