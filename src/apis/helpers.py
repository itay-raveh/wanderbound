"""Common helper functions for API modules."""

import asyncio
from typing import Any

import httpx

from ..logger import get_logger
from .cache import get_cached, set_cached
from .rate_limit import fetch_content_with_retry

logger = get_logger(__name__)

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
        return cached

    try:
        content = fetch_content_with_retry(
            url,
            timeout=timeout,
            calls_per_second=calls_per_second,
            max_attempts=max_attempts,
        )
        set_cached(cache_key, content)
        return content
    except Exception:
        return None


async def fetch_and_cache_json_async(
    client: httpx.AsyncClient,
    cache_key: str,
    url: str,
    timeout: float = 10.0,
    max_attempts: int = 3,
) -> dict[str, Any] | None:
    """Fetch JSON from URL with caching and async rate limiting.

    Checks cache first, then fetches if not cached, then caches the result.

    Args:
        client: httpx AsyncClient instance
        cache_key: Cache key for storing/retrieving the result
        url: URL to fetch JSON from
        timeout: Request timeout in seconds
        max_attempts: Maximum retry attempts

    Returns:
        JSON response as dictionary, or None if fetch fails
    """
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, dict):
        return cached

    for attempt in range(max_attempts):
        try:
            response = await client.get(url, timeout=timeout)
            response.raise_for_status()
            json_data = response.json()
            if not isinstance(json_data, dict):
                return None
            set_cached(cache_key, json_data)
            return json_data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait_time = 2**attempt
                logger.warning(f"Rate limited, waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
                continue
            logger.warning(f"HTTP error {e.response.status_code} for {url}: {e}")
            return None
        except (httpx.RequestError, httpx.HTTPError) as e:
            if attempt < max_attempts - 1:
                wait_time = 2**attempt
                logger.debug(f"Request failed, retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
            else:
                logger.warning(f"Failed to fetch {url} after {max_attempts} attempts: {e}")
                return None

    return None


async def fetch_and_cache_content_async(
    client: httpx.AsyncClient,
    cache_key: str,
    url: str,
    timeout: float = 10.0,
    max_attempts: int = 3,
) -> bytes | None:
    """Fetch binary content from URL with caching and async rate limiting.

    Checks cache first, then fetches if not cached, then caches the result.

    Args:
        client: httpx AsyncClient instance
        cache_key: Cache key for storing/retrieving the result
        url: URL to fetch content from
        timeout: Request timeout in seconds
        max_attempts: Maximum retry attempts

    Returns:
        Response content as bytes, or None if fetch fails
    """
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, bytes):
        return cached

    for attempt in range(max_attempts):
        try:
            response = await client.get(url, timeout=timeout)
            response.raise_for_status()
            content = response.content
            set_cached(cache_key, content)
            return content
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait_time = 2**attempt
                logger.warning(f"Rate limited, waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
                continue
            logger.warning(f"HTTP error {e.response.status_code} for {url}: {e}")
            return None
        except httpx.RequestError as e:
            if attempt < max_attempts - 1:
                wait_time = 2**attempt
                logger.debug(f"Request failed, retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
            else:
                logger.warning(f"Failed to fetch {url} after {max_attempts} attempts: {e}")
                return None

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
