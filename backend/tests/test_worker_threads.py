import threading
import time

import anyio

from app.core.worker_threads import run_sync


async def test_run_sync_respects_capacity_limiter() -> None:
    limiter = anyio.CapacityLimiter(1)
    active = 0
    peak = 0
    lock = threading.Lock()

    def work() -> None:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.01)
        with lock:
            active -= 1

    async def run_work() -> None:
        await run_sync(work, limiter=limiter)

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_work)
        tg.start_soon(run_work)

    assert peak == 1
