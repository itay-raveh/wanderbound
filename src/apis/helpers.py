"""Common helper functions for API modules."""

from typing import Any

from .cache import get_cached, set_cached
from .rate_limit import fetch_content_with_retry, fetch_json_with_retry, fetch_text_with_retry

__all__ = ["fetch_and_cache_json", "fetch_and_cache_content", "fetch_and_cache_text"]


def fetch_and_cache_json(
    cache_key: str,
    url: str,
    calls_per_second: int = 1,
    timeout: int = 10,
    max_attempts: int = 3,
    check_rate_limit: bool = False,
) -> dict[str, Any] | None:
    """Fetch JSON from URL with caching and rate limiting.

    Checks cache first, then fetches if not cached, then caches the result.

    Args:
        cache_key: Cache key for storing/retrieving the result.
        url: URL to fetch JSON from.
        calls_per_second: Maximum API calls per second.
        timeout: Request timeout in seconds.
        max_attempts: Maximum retry attempts.
        check_rate_limit: If True, raise RateLimitError on 429 status.

    Returns:
        JSON response as dictionary, or None if fetch fails.
    """
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, dict):
        return cached  # type: ignore[no-any-return]

    try:
        data = fetch_json_with_retry(
            url,
            timeout=timeout,
            calls_per_second=calls_per_second,
            max_attempts=max_attempts,
            check_rate_limit=check_rate_limit,
        )
        set_cached(cache_key, data)
        return data
    except Exception:
        return None


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
        return cached  # type: ignore[no-any-return]

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


def fetch_and_cache_text(
    cache_key: str,
    url: str,
    calls_per_second: int = 1,
    timeout: int = 10,
    max_attempts: int = 3,
) -> str | None:
    """Fetch text content from URL with caching and rate limiting.

    Checks cache first, then fetches if not cached, then caches the result.

    Args:
        cache_key: Cache key for storing/retrieving the result.
        url: URL to fetch text from.
        calls_per_second: Maximum API calls per second.
        timeout: Request timeout in seconds.
        max_attempts: Maximum retry attempts.

    Returns:
        Response content as text, or None if fetch fails.
    """
    cached = get_cached(cache_key)
    if cached is not None and isinstance(cached, str):
        return cached  # type: ignore[no-any-return]

    try:
        text = fetch_text_with_retry(
            url,
            timeout=timeout,
            calls_per_second=calls_per_second,
            max_attempts=max_attempts,
        )
        set_cached(cache_key, text)
        return text
    except Exception:
        return None
