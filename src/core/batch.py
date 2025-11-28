"""Generic batch processing utilities with concurrency control."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from src.core.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")


async def process_batch(
    items: list[T],
    process_func: Callable[[T, int], Awaitable[R]],
    *,
    concurrency: int = 5,
    progress_callback: Callable[[int], None] | None = None,
    stop_on_error: bool = False,
) -> list[R | Exception]:
    """Process a batch of items concurrently with a limit.

    Args:
        items: List of items to process.
        process_func: Async function that takes (item, index) and returns a result.
        concurrency: Maximum number of concurrent tasks.
        progress_callback: Optional callback function called with the number of completed tasks.
        stop_on_error: If True, stops processing on the first error.

    Returns:
        List of results or Exceptions, in the same order as the input items.
    """
    semaphore = asyncio.Semaphore(concurrency)
    results: list[R | Exception] = [None] * len(items)  # type: ignore[list-item]
    completed_count = 0

    async def _worker(item: T, index: int) -> None:
        nonlocal completed_count
        async with semaphore:
            try:
                result = await process_func(item, index)
                results[index] = result
            except Exception as e:
                logger.debug("Error processing item %d: %s", index, e)
                results[index] = e
                if stop_on_error:
                    raise
            finally:
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count)

    tasks = [_worker(item, i) for i, item in enumerate(items)]

    if stop_on_error:
        # If stop_on_error is True, gather will raise the first exception
        # We suppress it here because we return the results list which contains the exception
        # and we want to return whatever partial results we have.
        try:
            await asyncio.gather(*tasks)
        except Exception as e:  # noqa: BLE001
            logger.debug("Batch processing stopped due to error: %s", e)
    else:
        await asyncio.gather(*tasks, return_exceptions=True)

    return results
