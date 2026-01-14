from collections.abc import Callable, Iterable
from pathlib import Path

from aiohttp import web
from pydantic import BaseModel

from src.core.logger import get_logger
from src.data.layout import AlbumLayout, StepLayout

logger = get_logger(__name__)


class UpdateRequest(BaseModel):
    updates: list[StepLayout]


class EditorServer:
    def __init__(
        self,
        output_dir: Path,
        trip_dir: Path,
        regenerate_callback: Callable[[Iterable[int]], None],
    ) -> None:
        self.output_dir = output_dir
        self.trip_dir = trip_dir
        self.regenerate_callback = regenerate_callback
        self.layout_file = output_dir / "layout.json"

    async def handle_index(self, _request: web.Request) -> web.FileResponse:
        response = web.FileResponse(self.output_dir / "album.html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    async def handle_save_batch(self, request: web.Request) -> web.Response:
        update_request = UpdateRequest.model_validate(await request.json())
        current_layout = AlbumLayout.model_validate_json(self.layout_file.read_text())

        updated_layouts = {step_layout.id: step_layout for step_layout in update_request.updates}
        current_layout.steps.update(updated_layouts)
        self.layout_file.write_text(current_layout.model_dump_json(indent=2))

        self.regenerate_callback(updated_layouts.keys())

        return web.json_response({"success": True})

    def run(self, port: int = 8000) -> None:
        app = web.Application()

        app.router.add_get("/", self.handle_index)
        app.router.add_post("/api/save_batch", self.handle_save_batch)
        app.router.add_static(str(self.trip_dir.absolute()), self.trip_dir)

        web.run_app(app, port=port)
