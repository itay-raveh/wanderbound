import json
from pathlib import Path
from typing import Any

from aiohttp import web

from src.core.logger import get_logger
from src.core.settings import settings
from src.data.layout import AlbumLayout, StepLayout

logger = get_logger(__name__)


class EditorServer:
    def __init__(self, output_dir: Path, regenerate_callback: Any) -> None:
        self.output_dir = output_dir
        self.regenerate_callback = regenerate_callback
        self.layout_file = output_dir / "layout.json"

    async def handle_index(self, _request: web.Request) -> web.FileResponse:
        return web.FileResponse(self.output_dir / settings.file.album_html_file)

    async def handle_save(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            step_layout = StepLayout(**data)

            # Load existing layout or create new
            current_layout = AlbumLayout(steps={})
            if self.layout_file.exists():
                try:
                    current_layout = AlbumLayout.model_validate_json(self.layout_file.read_text())
                except (ValueError, TypeError, json.JSONDecodeError) as e:
                    logger.warning("Failed to parse existing layout.json, starting fresh: %s", e)

            # Update specific step
            current_layout.steps[step_layout.step_id] = step_layout

            # Save back to file
            self.layout_file.write_text(current_layout.model_dump_json(indent=2))

            # Trigger regeneration
            await self.regenerate_callback(step_layout.step_id)

            return web.json_response({"success": True})
        except Exception as e:
            logger.exception("Error saving layout")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    def run(self, port: int = 8000) -> None:
        app = web.Application()
        app.router.add_get("/", self.handle_index)
        app.router.add_post("/api/save", self.handle_save)

        # Serve static files from output directory
        app.router.add_static("/", self.output_dir)

        logger.info("Starting editor at http://localhost:%d", port)
        web.run_app(app, port=port)
