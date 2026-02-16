from __future__ import annotations

import asyncio
import itertools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Self

from psagen.core.cache import log_cache_stats
from psagen.core.client import APIClient
from psagen.core.logger import get_logger
from psagen.logic.altitude import fetch_all_altitudes
from psagen.logic.flags import fetch_flag
from psagen.logic.layout.builder import build_step_layout, try_build_layout
from psagen.logic.maps import fetch_map
from psagen.logic.media import extract_frame, load_photo
from psagen.logic.renderer import render_album_html
from psagen.logic.segments import Segment, load_segments
from psagen.logic.weather import fetch_weather
from psagen.models.enrich import EnrichedStep, Flag, Map, Weather
from psagen.models.layout import Video
from psagen.models.trip import Trip

if TYPE_CHECKING:
    from psagen.models.config import AlbumConfig
    from psagen.models.layout import StepLayout
    from psagen.models.trip import Step
    from psagen.models.user import User

logger = get_logger(__name__)

ProgressCallback = Callable[[str], None]


def _wp[**P, R](
    func: Callable[P, Awaitable[R]], callback: Callable[[], None]
) -> Callable[P, Awaitable[R]]:
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        result = await func(*args, **kwargs)
        callback()
        return result

    return wrapper


async def _enrich_steps(
    steps: list[Step], progress_callback: ProgressCallback
) -> list[EnrichedStep]:
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


@dataclass
class Album:
    user: User
    config: AlbumConfig
    steps: list[EnrichedStep]
    segments: list[Segment]

    @property
    def folder(self) -> Path:
        return self.user.trips_folder / self.config.trip_name

    @property
    def html_file(self) -> Path:
        return self.folder / "album.html"

    @classmethod
    async def generate(
        cls, user: User, config: AlbumConfig, progress_callback: ProgressCallback
    ) -> Self:
        progress_callback("Loading trip data...")
        trip_dir = user.trips_folder / config.trip_name
        trip_json_path = trip_dir / "trip.json"
        trip = Trip.model_validate_json(trip_json_path.read_bytes())
        progress_callback(f"Loaded trip {trip.name}")

        progress_callback("Fetching external data...")
        steps = await _enrich_steps(
            list(
                itertools.chain.from_iterable(
                    trip.all_steps[slc.as_slice()] for slc in config.settings.steps_ranges.root
                )
            ),
            progress_callback,
        )
        progress_callback(f"Fetched data for {len(steps)} steps")

        progress_callback("Building photo page layouts...")
        layouts = await asyncio.gather(
            *(
                _wp(
                    build_step_layout,
                    partial(
                        progress_callback,
                        f"{idx + 1}/{len(steps)} Built layout: {step.name}",
                    ),
                )(trip_dir, step)
                for idx, step in enumerate(steps)
                if step.id not in config.layouts
            )
        )
        config.layouts.update({layout.id: layout for layout in layouts})
        progress_callback(f"Built {len(layouts)} new page layouts")

        progress_callback("Loading location data...")
        segments = load_segments(
            trip_dir / "locations.json",
            [(step.location.lat, step.location.lon, step.start_time) for step in steps],
            steps[0].start_time,
            # Go until the END of the last day
            steps[-1].start_time + 60 * 60 * 24,
        )
        progress_callback(f"Loaded location data as {len(segments)} segments")

        log_cache_stats()

        album = cls(user=user, config=config, steps=steps, segments=segments)
        logger.info(
            "Generated %s: %d steps, %d segments",
            album.config.trip_name,
            len(album.steps),
            len(album.segments),
        )
        await asyncio.to_thread(album.save)
        logger.info("Generated %s", album.html_file)
        return album

    def persist_config(self) -> None:
        self.config.persist_in_trip_folder(self.folder)

    def save(self) -> None:
        self.persist_config()
        self.html_file.write_text(
            render_album_html(self.config.settings, self.config.layouts, self.steps, self.segments)
        )

    async def update_cover(self, step_id: int, new_cover: str) -> None:
        step_layout = self.config.layouts[step_id]
        old_cover = step_layout.cover
        step_layout.cover = Path(new_cover)

        # if the old cover was not in any of the pages
        if not any(
            old_cover in [photo.path for photo in page.photos] for page in step_layout.pages
        ):
            # then we need to find the page with the new cover,
            # and replace it with the old cover
            for page_idx, page in enumerate(step_layout.pages):
                for photo_idx, photo in enumerate(page.photos):
                    if photo.path == step_layout.cover:
                        # Replace new cover with old cover in the page
                        page.photos[photo_idx] = await load_photo(self.folder, old_cover)
                        # Make a layout for the page
                        step_layout.pages[page_idx] = try_build_layout(page.photos) or page
                        break

        self.save()

    async def update_video_timestamp(self, step_id: int, src: str, timestamp: float) -> None:
        src_path = Path(src)

        for page in self.config.layouts[step_id].pages:
            for asset in page.photos:
                if isinstance(asset, Video) and asset.src == src_path:
                    asset.timestamp = timestamp
                    frame_path = await extract_frame(
                        self.folder, self.folder / asset.src, asset.timestamp
                    )
                    asset.path = frame_path.relative_to(self.folder)
                    break

        self.save()

    async def update_layout(self, updates: list[StepLayout]) -> None:
        for step_layout in updates:
            step_layout.pages = [
                try_build_layout(page_layout.photos) or page_layout
                for page_layout in step_layout.pages
            ]
            self.config.layouts[step_layout.id] = step_layout

        self.save()
