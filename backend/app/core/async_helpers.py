import asyncio
from collections.abc import AsyncIterator, Coroutine, Iterable


async def yield_completed[T](
    coros: Iterable[Coroutine[object, object, T]],
) -> AsyncIterator[T]:
    """Yield results from coroutines as each completes (unordered)."""
    for coro in asyncio.as_completed(coros):
        yield await coro
