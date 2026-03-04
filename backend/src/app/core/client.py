# pyright: reportAny=false, reportExplicitAny=false

from typing import TYPE_CHECKING, Any, Self

import aiohttp
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

from app.core.logging import config_logger

if TYPE_CHECKING:
    from types import TracebackType

logger = config_logger(__name__)


class APIClient:
    """Async API client with caching, rate limiting, and retries."""

    def __init__(self, base_url: str | None = None) -> None:
        # Use a high connection limit (100) to allow speed but prevent "thundering herd"
        # timeouts. Keep timeout at 30s for safety.
        connector = aiohttp.TCPConnector(limit=100)
        timeout = aiohttp.ClientTimeout(total=30.0)

        self._client: aiohttp.ClientSession = aiohttp.ClientSession(
            base_url=base_url, connector=connector, timeout=timeout
        )

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get(
        self, url: str, params: dict[str, Any] | None = None
    ) -> bytes:
        try:
            async with self._client.get(url, params=params) as response:
                response.raise_for_status()
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
