# pyright: reportAny=false, reportExplicitAny=false

from hishel import AsyncSqliteStorage, BaseFilter, FilterPolicy, Response
from hishel.httpx import AsyncCacheTransport
from httpx import AsyncClient
from httpx_retries import Retry, RetryTransport

from app.core.logging import config_logger

config_logger("httpx")
config_logger("httpx_retries")


class _CacheOnlySuccess(BaseFilter[Response]):
    def needs_body(self) -> bool:
        return False

    def apply(self, item: Response, body: bytes | None) -> bool:  # noqa: ARG002
        return 200 <= item.status_code < 300


_policy = FilterPolicy(response_filters=[_CacheOnlySuccess()])
_policy.use_body_key = True

client = AsyncClient(
    follow_redirects=True,
    transport=AsyncCacheTransport(
        RetryTransport(retry=Retry(total=3, backoff_factor=0.5)),
        storage=AsyncSqliteStorage(default_ttl=60 * 60 * 24 * 30),  # type: ignore[arg-type]  # 30 days
        policy=_policy,
    ),
)
