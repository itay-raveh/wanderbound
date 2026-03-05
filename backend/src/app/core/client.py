# pyright: reportAny=false, reportExplicitAny=false

from typing import TYPE_CHECKING

from httpx import AsyncClient, HTTPError, HTTPStatusError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

from app.core.logging import config_logger

if TYPE_CHECKING:
    # noinspection PyProtectedMember
    from httpx._types import QueryParamTypes

logger = config_logger(__name__)


class RetryAsyncClient(AsyncClient):
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_with_retries(self, url: str, params: QueryParamTypes | None = None) -> bytes:
        try:
            response = await self.get(url, params=params)
            response.raise_for_status()
            return await response.aread()
        except HTTPStatusError as e:
            logger.warning(
                "HTTP error fetching %s: status=%d message=%s",
                url,
                e.response.status_code,
                await e.response.aread(),
            )
            raise
        except HTTPError as e:
            logger.warning("Request error fetching %s: %s", url, repr(e))
            raise
