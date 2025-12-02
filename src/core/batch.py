"""Generic batch processing utilities with concurrency control, rate limiting, and retries."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class BatchConfig:
    """Configuration for batch processing."""

    concurrency: int = 5
    retry_attempts: int = 3
    retry_min_wait: float = 1.0
    retry_max_wait: float = 10.0
    stop_on_error: bool = False


class BatchProcessor(Generic[T, R]):
    """Process a batch of items concurrently with rate limiting and retries."""

    def __init__(self, config: BatchConfig | None = None) -> None:
        self.config = config or BatchConfig()
        self.semaphore = asyncio.Semaphore(self.config.concurrency)
        self.retrier = AsyncRetrying(
            stop=stop_after_attempt(self.config.retry_attempts),
            wait=wait_exponential(min=self.config.retry_min_wait, max=self.config.retry_max_wait),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )

    async def process_item(
        self,
        item: T,
        _index: int,
        process_func: Callable[[T], Awaitable[R]],
    ) -> R:
        """Process a single item with concurrency control, rate limiting, and retries."""
        async with self.semaphore:
            async for attempt in self.retrier:
                with attempt:
                    return await process_func(item)
        # Should be unreachable due to reraise=True, but for type safety:
        raise RuntimeError("Unreachable")

    async def process_batch(
        self,
        items: list[T],
        process_func: Callable[[T], Awaitable[R]],
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[R | Exception]:
        """Process a batch of items."""
        results: list[R | Exception] = [None] * len(items)  # type: ignore[list-item]
        completed_count = 0

        async def _worker(item: T, index: int) -> None:
            nonlocal completed_count
            try:
                result = await self.process_item(item, index, process_func)
                results[index] = result
            except Exception as e:
                logger.debug("Error processing item %d: %s", index, e)
                results[index] = e
                if self.config.stop_on_error:
                    raise
            finally:
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count)

        tasks = [_worker(item, i) for i, item in enumerate(items)]

        if self.config.stop_on_error:
            try:
                await asyncio.gather(*tasks)
            except Exception as e:  # noqa: BLE001
                logger.debug("Batch processing stopped due to error: %s", e)
        else:
            await asyncio.gather(*tasks, return_exceptions=True)

        return results
