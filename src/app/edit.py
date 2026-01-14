from collections.abc import Callable
from pathlib import Path

from aiohttp import web

from src.core.logger import get_logger
from src.data.layout import AlbumLayout, StepLayout

logger = get_logger(__name__)


class EditorServer:
    def __init__(
        self,
        output_dir: Path,
        trip_dir: Path,
        regenerate_callback: Callable[[int], None],
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

    async def handle_save(self, request: web.Request) -> web.Response:
        try:
            step_layout = StepLayout.model_validate(await request.json())

            # Load existing layout or create new
            current_layout = AlbumLayout(steps={})
            if self.layout_file.exists():
                try:
                    current_layout = AlbumLayout.model_validate_json(self.layout_file.read_text())
                except (ValueError, TypeError) as e:
                    logger.warning("Failed to parse existing layout.json, starting fresh: %s", e)

            # Update specific step
            current_layout.steps[step_layout.id] = step_layout

            # Save back to file
            self.layout_file.write_text(current_layout.model_dump_json(indent=2))

            # Trigger regeneration
            self.regenerate_callback(step_layout.id)

            return web.json_response({"success": True})
        except Exception as e:
            logger.exception("Error saving layout")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def handle_save_batch(self, request: web.Request) -> web.Response:
        data: dict[str, list[StepLayout]] = await request.json()  # pyright: ignore[reportAny]
        current_layout = AlbumLayout.model_validate_json(self.layout_file.read_text())
        step_ids_to_regen = set[int]()

        for updated_layout in data.get("updates", []):
            step_layout = StepLayout.model_validate(updated_layout)
            current_layout.steps[step_layout.id] = step_layout
            step_ids_to_regen.add(step_layout.id)

        self.layout_file.write_text(current_layout.model_dump_json(indent=2))

        # Trigger regeneration for each step
        # TODO(itay): we should pass all IDs to regeneration to do it once if main supports it.
        for step_id in step_ids_to_regen:
            self.regenerate_callback(step_id)

        return web.json_response({"success": True})

    def run(self, port: int = 8000) -> None:
        app = web.Application()

        app.router.add_get("/", self.handle_index)
        app.router.add_post("/api/save", self.handle_save)
        app.router.add_post("/api/save_batch", self.handle_save_batch)

        app.router.add_static(str(self.trip_dir.absolute()), self.trip_dir)

        web.run_app(app, port=port)
