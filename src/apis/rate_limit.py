"""Rate limiting and retry utilities for API calls."""

from collections.abc import Callable
from typing import Any, TypeVar

import requests
from ratelimit import limits, sleep_and_retry
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

T = TypeVar("T")


class RateLimitError(Exception):
    """Raised when API returns 429 Too Many Requests."""


def with_rate_limit_and_retry(
    calls_per_second: int = 1,
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    retry_on: type[Exception] | tuple[type[Exception], ...] = requests.exceptions.RequestException,
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
    timeout: int,
    calls_per_second: int,
    max_attempts: int,
    check_rate_limit: bool,
    extract_response: Callable[[requests.Response], Any],
) -> Any:
    """Internal helper to fetch data with rate limiting and retry logic."""
    # For 429 errors, don't retry - they indicate we're rate limited
    # For other errors, retry up to max_attempts times
    retry_on: type[Exception] | tuple[type[Exception], ...] = requests.exceptions.RequestException
    if not check_rate_limit:
        # If not checking rate limits, also retry on RateLimitError (shouldn't happen)
        retry_on = (RateLimitError, requests.exceptions.RequestException)

    @with_rate_limit_and_retry(
        calls_per_second=calls_per_second,
        max_attempts=max_attempts,
        retry_on=retry_on,
    )
    def _fetch() -> Any:
        response = requests.get(url, timeout=timeout)

        if check_rate_limit and response.status_code == 429:
            # Don't retry 429 errors - raise immediately
            raise RateLimitError("Rate limited by API")

        response.raise_for_status()
        return extract_response(response)

    return _fetch()


def fetch_json_with_retry(
    url: str,
    timeout: int = 10,
    calls_per_second: int = 1,
    max_attempts: int = 3,
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
        requests.exceptions.RequestException: On other HTTP errors
    """
    result = _fetch_with_retry(
        url,
        timeout,
        calls_per_second,
        max_attempts,
        check_rate_limit,
        lambda r: r.json(),
    )
    assert isinstance(result, dict)
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
        requests.exceptions.RequestException: On HTTP errors
    """
    result = _fetch_with_retry(
        url, timeout, calls_per_second, max_attempts, False, lambda r: r.content
    )
    assert isinstance(result, bytes)
    return result


def fetch_text_with_retry(
    url: str,
    timeout: int = 10,
    calls_per_second: int = 1,
    max_attempts: int = 3,
) -> str:
    """Fetch text content from URL with rate limiting and retry logic.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        calls_per_second: Maximum number of API calls per second
        max_attempts: Maximum number of retry attempts

    Returns:
        Response content as text

    Raises:
        requests.exceptions.RequestException: On HTTP errors
    """
    result = _fetch_with_retry(
        url, timeout, calls_per_second, max_attempts, False, lambda r: r.text
    )
    assert isinstance(result, str)
    return result
