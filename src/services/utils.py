"""Shared utilities for services: caching, rate limiting, and helpers."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict, TypeVar, cast

import httpx
import typed_diskcache as diskcache
from ratelimit import limits, sleep_and_retry
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.logger import get_logger

logger = get_logger(__name__)

# --- Cache Configuration ---

CACHE_DIR = Path.home() / ".cache" / "polarsteps-album-generator"
CACHE_DIR.mkdir(exist_ok=True)

# Create diskcache instance with LRU eviction policy
_cache = diskcache.Cache(str(CACHE_DIR), size_limit=2**30, eviction_policy="least-recently-used")


def get_cached(key: str) -> Any | None:
    """Get cached API response."""
    try:
        result = _cache.get(key, default=None)
    except (OSError, PermissionError, AttributeError) as e:
        logger.debug("Error getting cached value for key '%s': %s", key, e)
        return None
    except Exception as e:  # noqa: BLE001
        error_type_name = type(e).__name__
        if "CompileError" in error_type_name or "SQLAlchemyError" in error_type_name:
            logger.debug(
                "SQLAlchemy error getting cached value for key '%s': %s", key, error_type_name
            )
            return None
        logger.debug("Unexpected error getting cached value for key '%s': %s", key, error_type_name)
        return None
    else:
        return result


def set_cached(key: str, value: Any) -> None:
    """Cache API response."""
    try:
        _cache.set(key, value)
    except (OSError, PermissionError) as e:
        logger.debug("Error setting cached value for key '%s': %s", key, e)
    except Exception as e:  # noqa: BLE001
        error_type_name = type(e).__name__
        if "CompileError" in error_type_name or "SQLAlchemyError" in error_type_name:
            logger.debug(
                "SQLAlchemy error setting cached value for key '%s': %s", key, error_type_name
            )
        else:
            logger.debug(
                "Unexpected error setting cached value for key '%s': %s", key, error_type_name
            )


# --- Rate Limiting & Retry ---

T = TypeVar("T")
HTTP_STATUS_TOO_MANY_REQUESTS = 429
BACKOFF_BASE = 2


class FetchConfig(TypedDict, total=False):
    """Configuration for fetch operations with retry logic."""

    timeout: int
    calls_per_second: int
    max_attempts: int


class RateLimitError(Exception):
    """Raised when API returns 429 Too Many Requests."""


def with_rate_limit_and_retry(
    calls_per_second: int = 1,
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    retry_on: type[Exception] | tuple[type[Exception], ...] = httpx.RequestError,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Create a decorator that adds rate limiting and retry logic to a function."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @sleep_and_retry  # type: ignore[misc]
        @limits(calls=calls_per_second, period=1)  # type: ignore[misc]
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type(retry_on),
            reraise=True,
        )
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return func(*args, **kwargs)

        return wrapper  # type: ignore[no-any-return]

    return decorator


def _fetch_with_retry(
    url: str,
    config: FetchConfig,
    *,
    check_rate_limit: bool,
    extract_response: Callable[[httpx.Response], Any],
) -> Any:
    """Internal helper to fetch data with rate limiting and retry logic."""
    timeout = config.get("timeout", 10)
    calls_per_second = config.get("calls_per_second", 1)
    max_attempts = config.get("max_attempts", 3)

    retry_on: type[Exception] | tuple[type[Exception], ...] = httpx.RequestError
    if not check_rate_limit:
        retry_on = (RateLimitError, httpx.RequestError)

    @with_rate_limit_and_retry(
        calls_per_second=calls_per_second,
        max_attempts=max_attempts,
        retry_on=retry_on,
    )
    def _fetch() -> Any:
        response = httpx.get(url, timeout=timeout)

        if check_rate_limit and response.status_code == 429:
            msg = "Rate limited by API"
            raise RateLimitError(msg)

        response.raise_for_status()
        return extract_response(response)

    return _fetch()


def fetch_json_with_retry(
    url: str,
    timeout: int = 10,
    calls_per_second: int = 1,
    max_attempts: int = 3,
    *,
    check_rate_limit: bool = False,
) -> dict[str, Any]:
    """Fetch JSON data from URL with rate limiting and retry logic."""
    config: FetchConfig = {
        "timeout": timeout,
        "calls_per_second": calls_per_second,
        "max_attempts": max_attempts,
    }
    result = _fetch_with_retry(
        url, config, check_rate_limit=check_rate_limit, extract_response=lambda r: r.json()
    )
    if not isinstance(result, dict):
        raise TypeError(f"Expected dict from JSON response, got {type(result).__name__}")
    return result


def fetch_content_with_retry(
    url: str,
    timeout: int = 10,
    calls_per_second: int = 1,
    max_attempts: int = 3,
) -> bytes:
    """Fetch binary content from URL with rate limiting and retry logic."""
    result = _fetch_with_retry(
        url,
        {"timeout": timeout, "calls_per_second": calls_per_second, "max_attempts": max_attempts},
        check_rate_limit=False,
        extract_response=lambda r: r.content,
    )
    if not isinstance(result, bytes):
        raise TypeError(f"Expected bytes from content response, got {type(result).__name__}")
    return result


# --- Async Helpers ---


def create_async_client(limits: httpx.Limits | None = None) -> httpx.AsyncClient:
    """Create an httpx AsyncClient with appropriate limits."""
    if limits is None:
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    return httpx.AsyncClient(limits=limits, timeout=30.0)


async def fetch_and_cache_json_async(
    client: httpx.AsyncClient,
    cache_key: str,
    url: str,
    *,
    request_timeout: float = 10.0,
    max_attempts: int = 3,
) -> dict[str, Any] | None:
    """Fetch JSON from URL with caching and async rate limiting."""
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, dict):
        return cast("dict[str, Any]", cached)

    for attempt in range(max_attempts):
        try:
            response = await client.get(url, timeout=request_timeout)
            response.raise_for_status()
            json_data = response.json()
            if not isinstance(json_data, dict):
                return None
            set_cached(cache_key, json_data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == HTTP_STATUS_TOO_MANY_REQUESTS:
                wait_time = BACKOFF_BASE**attempt
                logger.warning("Rate limited, waiting %ds before retry...", wait_time)
                await asyncio.sleep(wait_time)
                continue
            logger.warning("HTTP error %d for %s: %s", e.response.status_code, url, e)
            return None
        except (httpx.RequestError, httpx.HTTPError) as e:
            if attempt < max_attempts - 1:
                wait_time = BACKOFF_BASE**attempt
                logger.debug("Request failed, retrying in %ds: %s", wait_time, e)
                await asyncio.sleep(wait_time)
            else:
                logger.warning("Failed to fetch %s after %d attempts: %s", url, max_attempts, e)
                return None
        else:
            return json_data

    return None


async def fetch_and_cache_content_async(
    client: httpx.AsyncClient,
    cache_key: str,
    url: str,
    *,
    request_timeout: float = 10.0,
    max_attempts: int = 3,
) -> bytes | None:
    """Fetch binary content from URL with caching and async rate limiting."""
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, bytes):
        return cast("bytes", cached)

    for attempt in range(max_attempts):
        try:
            response = await client.get(url, timeout=request_timeout)
            response.raise_for_status()
            content = response.content
            set_cached(cache_key, content)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == HTTP_STATUS_TOO_MANY_REQUESTS:
                wait_time = BACKOFF_BASE**attempt
                logger.warning("Rate limited, waiting %ds before retry...", wait_time)
                await asyncio.sleep(wait_time)
                continue
            logger.warning("HTTP error %d for %s: %s", e.response.status_code, url, e)
            return None
        except httpx.RequestError as e:
            if attempt < max_attempts - 1:
                wait_time = BACKOFF_BASE**attempt
                logger.debug("Request failed, retrying in %ds: %s", wait_time, e)
                await asyncio.sleep(wait_time)
            else:
                logger.warning("Failed to fetch %s after %d attempts: %s", url, max_attempts, e)
                return None
        else:
            return content

    return None


def fetch_and_cache_content(
    cache_key: str,
    url: str,
    calls_per_second: int = 1,
    timeout: int = 10,
    max_attempts: int = 3,
) -> bytes | None:
    """Fetch binary content from URL with caching and rate limiting."""
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, bytes):
        return cast("bytes", cached)

    try:
        content = fetch_content_with_retry(
            url,
            timeout=timeout,
            calls_per_second=calls_per_second,
            max_attempts=max_attempts,
        )
        set_cached(cache_key, content)
    except (httpx.RequestError, httpx.HTTPStatusError, OSError):
        return None
    else:
        return content
