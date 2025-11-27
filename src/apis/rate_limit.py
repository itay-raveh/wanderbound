"""Rate limiting and retry utilities for API calls."""

from collections.abc import Callable
from typing import Any, TypedDict, TypeVar

import httpx
from ratelimit import limits, sleep_and_retry
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

T = TypeVar("T")


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
    """Create a decorator that adds rate limiting and retry logic to a function.

    Args:
        calls_per_second: Maximum number of API calls per second
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)
        retry_on: Exception type(s) to retry on

    Returns:
        Decorator function that adds rate limiting and retry logic
    """

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

    # For 429 errors, don't retry - they indicate we're rate limited
    # For other errors, retry up to max_attempts times
    retry_on: type[Exception] | tuple[type[Exception], ...] = httpx.RequestError
    if not check_rate_limit:
        # If not checking rate limits, also retry on RateLimitError (shouldn't happen)
        retry_on = (RateLimitError, httpx.RequestError)

    @with_rate_limit_and_retry(
        calls_per_second=calls_per_second,
        max_attempts=max_attempts,
        retry_on=retry_on,
    )
    def _fetch() -> Any:
        response = httpx.get(url, timeout=timeout)

        if check_rate_limit and response.status_code == 429:
            # Don't retry 429 errors - raise immediately
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
    """Fetch JSON data from URL with rate limiting and retry logic.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        calls_per_second: Maximum number of API calls per second
        max_attempts: Maximum number of retry attempts
        check_rate_limit: If True, raise RateLimitError on 429 status code

    Returns:
        JSON response data as dictionary

    Raises:
        RateLimitError: If check_rate_limit is True and status code is 429
        httpx.RequestError: On HTTP or network errors
    """
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
    """Fetch binary content from URL with rate limiting and retry logic.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        calls_per_second: Maximum number of API calls per second
        max_attempts: Maximum number of retry attempts

    Returns:
        Response content as bytes

    Raises:
        httpx.HTTPError: On HTTP errors
    """
    result = _fetch_with_retry(
        url,
        {"timeout": timeout, "calls_per_second": calls_per_second, "max_attempts": max_attempts},
        check_rate_limit=False,
        extract_response=lambda r: r.content,
    )
    if not isinstance(result, bytes):
        raise TypeError(f"Expected bytes from content response, got {type(result).__name__}")
    return result
