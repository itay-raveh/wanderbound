from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Self

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
from psagen.models.enrich import EnrichedStep
from psagen.models.layout import Video
from psagen.models.trip import Trip

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from psagen.models.config import AlbumConfig
    from psagen.models.layout import StepLayout
    from psagen.models.trip import Step
    from psagen.models.user import User

logger = get_logger(__name__)


async def _enrich_steps(steps: list[Step]) -> list[EnrichedStep]:
    """Fetch all external data concurrently."""
    async with APIClient() as client:
        results = await asyncio.gather(
            *(
                asyncio.gather(
                    fetch_weather(client, step),
                    fetch_flag(client, step.location.country_code),
                    fetch_map(
                        client,
                        step.location.lat,
                        step.location.lon,
                        step.location.country_code,
                    ),
                )
                for step in steps
            ),
        )

        alts = await fetch_all_altitudes(
            client, [(step.location.lat, step.location.lon) for step in steps]
        )

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
    async def generate(cls, user: User, config: AlbumConfig) -> AsyncGenerator[str | Self]:
        yield "Loading trip data..."
        trip_dir = user.trips_folder / config.trip_name
        trip_json_path = trip_dir / "trip.json"
        trip = Trip.model_validate_json(trip_json_path.read_bytes())
        yield f"Loaded trip {trip.name}"

        yield "Fetching external data..."
        steps = await _enrich_steps(
            list(
                itertools.chain.from_iterable(
                    trip.all_steps[slc.as_slice()] for slc in config.settings.steps_ranges.root
                )
            )
        )
        yield f"Fetched data for {len(steps)} steps"

        yield "Building photo page layouts..."
        layouts = await asyncio.gather(
            *(build_step_layout(trip_dir, step) for step in steps if step.id not in config.layouts)
        )
        config.layouts.update({layout.id: layout for layout in layouts})
        yield f"Built {len(layouts)} new page layouts"

        yield "Loading location data..."
        segments = load_segments(
            trip_dir / "locations.json",
            [(step.location.lat, step.location.lon, step.start_time) for step in steps],
            steps[0].start_time,
            # Go until the END of the last day
            steps[-1].start_time + 60 * 60 * 24,
        )
        yield f"Loaded location data as {len(segments)} segments"

        yield cls(user=user, config=config, steps=steps, segments=segments)

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
