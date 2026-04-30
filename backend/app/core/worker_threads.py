import functools
from collections.abc import Callable
from typing import Any

import anyio
from anyio import to_thread


async def run_sync[T](
    func: Callable[..., T],
    *args: Any,
    limiter: anyio.CapacityLimiter | None = None,
    **kwargs: Any,
) -> T:
    if kwargs:
        func = functools.partial(func, **kwargs)
    return await to_thread.run_sync(func, *args, limiter=limiter)
