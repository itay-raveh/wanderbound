from __future__ import annotations

import asyncio
import itertools
import pathlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from psagen.core.cache import log_cache_stats
from psagen.core.logger import get_logger
from psagen.logic.enrich import enrich_steps
from psagen.logic.layout.builder import build_step_layout
from psagen.logic.media import extract_frame
from psagen.logic.renderer import render_album_html
from psagen.logic.segments import Locations, Segment, load_segments
from psagen.models.layout import Video
from psagen.models.trip import Trip

if TYPE_CHECKING:
    import anyio

    from psagen.logic.enrich import EnrichedStep
    from psagen.models.config import AlbumConfig
    from psagen.models.user import User

logger = get_logger(__name__)

ProgressCallback = Callable[[str], None]


@dataclass
class Album:
    user: User
    config: AlbumConfig
    steps: list[EnrichedStep]
    segments: list[Segment]

    @property
    def folder(self) -> anyio.Path:
        return self.user.trips_folder / self.config.trip_name

    @property
    def html_file(self) -> anyio.Path:
        return self.folder / "album.html"

    @classmethod
    async def generate(
        cls, user: User, config: AlbumConfig, progress_callback: ProgressCallback
    ) -> Self:
        trip_dir = user.trips_folder / config.trip_name

        progress_callback("Loading trip data...")
        trip = Trip.model_validate_json(await (trip_dir / "trip.json").read_bytes())
        progress_callback(f"Loaded trip {trip.name}")

        steps = await enrich_steps(
            list(
                itertools.chain.from_iterable(
                    trip.all_steps[slc.as_slice()] for slc in config.settings.steps_ranges.root
                )
            ),
            progress_callback,
        )

        progress_callback("Building photo page layouts...")
        async for future in asyncio.as_completed(
            build_step_layout(trip_dir, step) for step in steps if step.id not in config.layouts
        ):
            layout = await future
            progress_callback(f"Built layout: {layout.name}")
            config.layouts[layout.id] = layout
        progress_callback("Built new page layouts")

        locations = Locations.model_validate_json(await (trip_dir / "locations.json").read_bytes())
        segments = await load_segments(locations, steps, progress_callback)

        album = cls(user=user, config=config, steps=steps, segments=segments)
        logger.info(
            "Generated /%s: %d steps, %d segments",
            album.config.trip_name,
            len(album.steps),
            len(album.segments),
        )

        await album.save()
        logger.info("Generated /%s", album.html_file.relative_to(user.trips_folder))

        log_cache_stats()
        return album

    async def persist_config(self) -> None:
        await self.config.persist_for(self.user)

    async def save(self) -> None:
        await self.persist_config()
        await self.html_file.write_text(
            render_album_html(self.config.settings, self.config.layouts, self.steps, self.segments)
        )

    async def update_video_timestamp(self, step_id: int, src: str, timestamp: float) -> None:
        src_path = pathlib.Path(src)

        for page in self.config.layouts[step_id].pages:
            for asset in page.photos:
                if isinstance(asset, Video) and asset.src == src_path:
                    asset.timestamp = timestamp
                    frame_path = await extract_frame(
                        self.folder, self.folder / asset.src, asset.timestamp
                    )
                    asset.path = pathlib.Path(frame_path.relative_to(self.folder))
                    break

        await self.save()
