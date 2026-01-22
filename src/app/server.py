import asyncio
from collections.abc import Sequence
from pathlib import Path

from aiohttp import web
from pydantic import BaseModel
from rich import get_console

from src.app.args import Args
from src.app.renderer import build_overview_template_ctx, render_album_html
from src.core.logger import create_progress, get_logger
from src.core.settings import settings
from src.layout.builder import build_step_layout, try_build_layout
from src.models.context import TripTemplateCtx
from src.models.layout import AlbumLayout, StepLayout, Video
from src.models.trip import EnrichedStep, Location
from src.services.media import extract_frame, frame_path, load_photo

logger = get_logger(__name__)


class CoverRequest(BaseModel):
    id: int
    cover: Path


class VideoUpdateRequest(BaseModel):
    id: int
    src: Path
    timestamp: float


class LayoutRequest(BaseModel):
    updates: list[StepLayout]


class EditorServer:
    def __init__(
        self,
        args: Args,
        trip_ctx: TripTemplateCtx,
        steps: Sequence[EnrichedStep],
        home_location: tuple[Location, str],
    ) -> None:
        self.trip_ctx = trip_ctx
        self.output_dir = Path(args.output)
        self.trip_dir = Path(args.trip)
        self.layout_file = self.output_dir / "layout.json"
        self.steps = steps
        self.maps_slices = args.maps
        self.home_location = home_location

    async def generate(self, target_ids: Sequence[int]) -> None:
        logger.info("Generating steps %s", target_ids)

        layout = (
            AlbumLayout.model_validate_json(self.layout_file.read_bytes())
            if self.layout_file.exists()
            else AlbumLayout(steps={})
        )

        with create_progress("Loading photos/videos") as progress:
            for step in progress.track(
                [step for step in self.steps if step.id in target_ids],
                description="Building layouts...",
            ):
                if step.id not in layout.steps:
                    layout.steps[step.id] = await build_step_layout(
                        step, self.trip_dir, self.output_dir
                    )

        self.layout_file.write_text(layout.model_dump_json(indent=2))
        logger.info("Generated: %s", self.layout_file, extra={"success": True})

        overview_ctx = build_overview_template_ctx(
            self.steps, layout, self.trip_ctx.segments, self.home_location
        )

        with get_console().status("[bold blue]Generating HTML..."):
            html = render_album_html(
                self.steps, layout, self.trip_ctx, overview_ctx, self.maps_slices or []
            )

        html_file = self.output_dir / "album.html"
        html_file.write_text(html)
        logger.info("Generated: %s", html_file, extra={"success": True})

    async def handle_index(self, _request: web.Request) -> web.FileResponse:
        response = web.FileResponse(self.output_dir / "album.html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    async def handle_cover(self, request: web.Request) -> web.Response:
        cover_request = CoverRequest.model_validate(await request.json())
        layout = AlbumLayout.model_validate_json(self.layout_file.read_text())

        # Replace cover
        step_layout = layout.steps[cover_request.id]
        old_cover = step_layout.cover
        step_layout.cover = cover_request.cover

        # if the old cover was not in any of the pages
        if not any(
            old_cover in [photo.path for photo in page.photos] for page in step_layout.pages
        ):
            # then we need to find the page with the new cover,
            # and replace it with the old cover
            for page in step_layout.pages:
                for idx, photo in enumerate(page.photos):
                    if photo.path == cover_request.cover:
                        page.photos[idx] = await load_photo(old_cover)
                        break

        self.layout_file.write_text(layout.model_dump_json(indent=2))
        await self.generate([cover_request.id])
        return web.json_response({"success": True})

    async def handle_video(self, request: web.Request) -> web.Response:
        video_request = VideoUpdateRequest.model_validate(await request.json())
        layout = AlbumLayout.model_validate_json(self.layout_file.read_text())

        for page in layout.steps[video_request.id].pages:
            for photo in page.photos:
                if isinstance(photo, Video) and photo.src == video_request.src:
                    photo.path = frame_path(
                        video_request.src, video_request.timestamp, self.output_dir
                    )
                    photo.timestamp = video_request.timestamp
                    await extract_frame(photo.src, photo.timestamp, photo.path)
                    break

        self.layout_file.write_text(layout.model_dump_json(indent=2))
        await self.generate([video_request.id])
        return web.json_response({"success": True})

    async def handle_layout(self, request: web.Request) -> web.Response:
        layout_request = LayoutRequest.model_validate(await request.json())
        layout = AlbumLayout.model_validate_json(self.layout_file.read_text())

        for step_layout in layout_request.updates:
            step_layout.pages = [
                try_build_layout(page_layout.photos) or page_layout
                for page_layout in step_layout.pages
            ]
            layout.steps[step_layout.id] = step_layout

        self.layout_file.write_text(layout.model_dump_json(indent=2))
        await self.generate([step_layout.id for step_layout in layout_request.updates])
        return web.json_response({"success": True})

    async def run(self) -> None:
        app = web.Application(logger=logger)

        app.router.add_get("/", self.handle_index)
        app.router.add_post("/api/cover", self.handle_cover)
        app.router.add_post("/api/layout", self.handle_layout)
        app.router.add_post("/api/video", self.handle_video)
        app.router.add_static(str(self.trip_dir.absolute()), self.trip_dir)
        app.router.add_static(str(self.output_dir.absolute()), self.output_dir)

        runner = web.AppRunner(app, handle_signals=True)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", settings.editor_port)
        await site.start()

        try:
            while True:
                await asyncio.Event().wait()
        finally:
            await runner.cleanup()
