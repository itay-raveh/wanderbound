from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING

from psagen.core.cache import async_cache
from psagen.core.client import APIClient
from psagen.logic.altitude import fetch_all_altitudes
from psagen.logic.flags import Flag, fetch_flag
from psagen.logic.maps import fetch_map
from psagen.logic.maps.service import Map  # noqa: TC001
from psagen.logic.weather import Weather, fetch_weather
from psagen.models.trip import Step

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class EnrichedStep(Step):
    altitude: float
    weather: Weather
    flag: Flag
    map: Map


def _wp[**P, R](
    func: Callable[P, Awaitable[R]], callback: Callable[[], None]
) -> Callable[P, Awaitable[R]]:
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        result = await func(*args, **kwargs)
        callback()
        return result

    return wrapper


@async_cache
async def enrich_steps(
    steps: list[Step], progress_callback: Callable[[str], None]
) -> list[EnrichedStep]:
    progress_callback("Fetching external data...")

    async with APIClient() as client:
        tasks: list[asyncio.Future[tuple[Weather, Flag, Map]]] = []
        total = len(steps)
        for idx, step in enumerate(steps):
            _weather = _wp(
                fetch_weather, partial(progress_callback, f"{idx + 1}/{total} Fetched weather")
            )
            _flag = _wp(fetch_flag, partial(progress_callback, f"{idx + 1}/{total} Fetched flag"))
            _map = _wp(fetch_map, partial(progress_callback, f"{idx + 1}/{total} Fetched map"))

            tasks.append(
                asyncio.gather(
                    _weather(client, step),
                    _flag(client, step.location.country_code),
                    _map(
                        client,
                        round(step.location.lat, 1),
                        round(step.location.lon, 1),
                        step.location.country_code,
                    ),
                )
            )

        results = await asyncio.gather(*tasks)

        progress_callback("Fetching altitudes....")
        alts = await fetch_all_altitudes(
            client,
            [
                (
                    round(step.location.lat, 4),
                    round(step.location.lon, 4),
                )
                for step in steps
            ],
        )
        progress_callback(f"Fetched {len(alts)} altitudes")

    progress_callback(f"Fetched data for {len(steps)} steps")
    return [
        EnrichedStep(
            **step.model_dump(by_alias=True),  # pyright: ignore[reportAny]
            altitude=altitude,
            weather=weather,
            flag=flag,
            map=map_,
        )
        for step, altitude, (weather, flag, map_) in zip(steps, alts, results, strict=True)
    ]
