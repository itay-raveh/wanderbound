from collections.abc import Callable, Sequence
from pathlib import Path

from aiohttp import web
from pydantic import BaseModel

from src.core.logger import get_logger
from src.data.layout import AlbumLayout, StepLayout
from src.layout.processor import load_photo
from src.layout.scorer import try_choose_layout

logger = get_logger(__name__)


class CoverRequest(BaseModel):
    id: int
    cover: Path


class LayoutRequest(BaseModel):
    updates: list[StepLayout]


class EditorServer:
    def __init__(
        self,
        output_dir: Path,
        trip_dir: Path,
        regenerate_callback: Callable[[Sequence[int]], None],
    ) -> None:
        self.output_dir = output_dir
        self.trip_dir = trip_dir
        self.regenerate = regenerate_callback
        self.layout_file = output_dir / "layout.json"

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
                        page.photos[idx] = load_photo(old_cover)
                        break

        self.layout_file.write_text(layout.model_dump_json(indent=2))
        self.regenerate([cover_request.id])
        return web.json_response({"success": True})

    async def handle_layout(self, request: web.Request) -> web.Response:
        layout_request = LayoutRequest.model_validate(await request.json())
        layout = AlbumLayout.model_validate_json(self.layout_file.read_text())

        for step_layout in layout_request.updates:
            step_layout.pages = [
                try_choose_layout(page_layout.photos) or page_layout
                for page_layout in step_layout.pages
            ]
            layout.steps[step_layout.id] = step_layout

        self.layout_file.write_text(layout.model_dump_json(indent=2))
        self.regenerate([step_layout.id for step_layout in layout_request.updates])
        return web.json_response({"success": True})

    def run(self, port: int = 8000) -> None:
        app = web.Application()

        app.router.add_get("/", self.handle_index)
        app.router.add_post("/api/cover", self.handle_cover)
        app.router.add_post("/api/layout", self.handle_layout)
        app.router.add_static(str(self.trip_dir.absolute()), self.trip_dir)

        web.run_app(app, port=port)
