"""Common helper functions for API modules."""

import asyncio
from typing import Any, cast

import httpx

from src.logger import get_logger

from .cache import get_cached, set_cached
from .rate_limit import fetch_content_with_retry

logger = get_logger(__name__)

# HTTP status code constants
HTTP_STATUS_TOO_MANY_REQUESTS = 429

# Exponential backoff base for retries
BACKOFF_BASE = 2

__all__ = [
    "create_async_client",
    "fetch_and_cache_content",
    "fetch_and_cache_content_async",
    "fetch_and_cache_json_async",
]


def fetch_and_cache_content(
    cache_key: str,
    url: str,
    calls_per_second: int = 1,
    timeout: int = 10,
    max_attempts: int = 3,
) -> bytes | None:
    """Fetch binary content from URL with caching and rate limiting.

    Checks cache first, then fetches if not cached, then caches the result.

    Args:
        cache_key: Cache key for storing/retrieving the result.
        url: URL to fetch content from.
        calls_per_second: Maximum API calls per second.
        timeout: Request timeout in seconds.
        max_attempts: Maximum retry attempts.

    Returns:
        Response content as bytes, or None if fetch fails.
    """
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


async def fetch_and_cache_json_async(
    client: httpx.AsyncClient,
    cache_key: str,
    url: str,
    *,
    request_timeout: float = 10.0,
    max_attempts: int = 3,
) -> dict[str, Any] | None:
    """Fetch JSON from URL with caching and async rate limiting.

    Checks cache first, then fetches if not cached, then caches the result.

    Args:
        client: httpx AsyncClient instance
        cache_key: Cache key for storing/retrieving the result
        url: URL to fetch JSON from
        request_timeout: Request timeout in seconds
        max_attempts: Maximum retry attempts

    Returns:
        JSON response as dictionary, or None if fetch fails
    """
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
    """Fetch binary content from URL with caching and async rate limiting.

    Checks cache first, then fetches if not cached, then caches the result.

    Args:
        client: httpx AsyncClient instance
        cache_key: Cache key for storing/retrieving the result
        url: URL to fetch content from
        request_timeout: Request timeout in seconds
        max_attempts: Maximum retry attempts

    Returns:
        Response content as bytes, or None if fetch fails
    """
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


def create_async_client(limits: httpx.Limits | None = None) -> httpx.AsyncClient:
    """Create an httpx AsyncClient with appropriate limits.

    Args:
        limits: Optional httpx.Limits instance for connection pooling

    Returns:
        Configured httpx.AsyncClient instance
    """
    if limits is None:
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    return httpx.AsyncClient(limits=limits, timeout=30.0)
