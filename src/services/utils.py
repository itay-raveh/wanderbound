"""Shared utilities for services: API client and helpers."""

from typing import Any

import httpx
from aiolimiter import AsyncLimiter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.cache import DATA_CACHE_DIR, get_cached, set_cached
from src.core.logger import get_logger
from src.services.http_cache import create_cached_client

logger = get_logger(__name__)

# Re-export for compatibility
CACHE_DIR = DATA_CACHE_DIR


class APIClient:
    """Async API client with caching, rate limiting, and retries."""

    def __init__(
        self,
        base_url: str = "",
        rate_limit: float = 5.0,  # calls per second
        retries: int = 3,
        timeout: float = 30.0,
    ) -> None:
        self.client = create_cached_client(timeout=timeout)
        self.client.base_url = httpx.URL(base_url)
        self.limiter = AsyncLimiter(max_rate=rate_limit, time_period=1.0)
        self.retries = retries

    async def close(self) -> None:
        await self.client.aclose()

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch JSON data with rate limiting and retries."""
        data = await self._fetch(url, params=params, response_type="json")
        return dict(data)

    async def get_content(self, url: str, params: dict[str, Any] | None = None) -> bytes:
        """Fetch binary content with rate limiting and retries."""
        content = await self._fetch(url, params=params, response_type="content")
        return bytes(content)

    async def _fetch(self, url: str, params: dict[str, Any] | None, response_type: str) -> Any:
        @retry(
            stop=stop_after_attempt(self.retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            reraise=True,
        )
        async def _make_request() -> Any:
            async with self.limiter:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                if response_type == "json":
                    return response.json()
                return response.content

        try:
            return await _make_request()
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            raise


__all__ = ["CACHE_DIR", "APIClient", "get_cached", "set_cached"]
