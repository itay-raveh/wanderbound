# pyright: reportAny=false, reportExplicitAny=false

from hishel.httpx import AsyncCacheTransport
from httpx import AsyncClient
from httpx_retries import Retry, RetryTransport

from app.core.logging import config_logger

config_logger("httpx")
config_logger("httpx_retries")


client = AsyncClient(
    follow_redirects=True,
    transport=AsyncCacheTransport(
        RetryTransport(
            retry=Retry(
                total=5,
                backoff_factor=1,
            )
        )
    ),
)
