"""Shared utilities for services: API client and helpers."""

from types import TracebackType
from typing import Any

import aiohttp
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

    def __init__(self, base_url: str | None = None) -> None:
        # Use a high connection limit (100) to allow speed but prevent "thundering herd"
        # timeouts. Keep timeout at 30s for safety.
        connector = aiohttp.TCPConnector(limit=100)
        timeout = aiohttp.ClientTimeout(total=30.0)

        # aiohttp requires base_url to be absolute if provided.
        # If it's empty, we should pass None.
        self._client = aiohttp.ClientSession(
            base_url=base_url, connector=connector, timeout=timeout
        )

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> "APIClient":
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    def __getstate__(self) -> None:
        """Return None state for pickling to ensure constant cache key."""
        return

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
            lambda exc: isinstance(exc, aiohttp.ClientResponseError) and exc.status >= 500
        ),
        reraise=True,
    )
    async def _fetch(self, url: str, params: dict[str, Any] | None, response_type: str) -> Any:
        try:
            async with self._client.get(url, params=params) as response:
                response.raise_for_status()
                if response_type == "json":
                    return await response.json()
                return await response.read()
        except aiohttp.ClientResponseError as e:
            logger.warning(
                "HTTP error fetching %s: status=%d message=%s",
                url,
                e.status,
                e.message,
            )
            raise
        except aiohttp.ClientError as e:
            logger.warning("Request error fetching %s: %s", url, repr(e))
            raise
        except Exception as e:
            logger.warning("Unexpected error fetching %s: %s", url, repr(e))
            raise
