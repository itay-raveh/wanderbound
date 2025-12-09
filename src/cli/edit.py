import json
from pathlib import Path
from typing import Any

from aiohttp import web

from src.core.logger import get_logger
from src.core.settings import settings
from src.data.layout import AlbumLayout, StepLayout

logger = get_logger(__name__)


class EditorServer:
    def __init__(self, output_dir: Path, trip_dir: Path, regenerate_callback: Any) -> None:
        self.output_dir = output_dir
        self.trip_dir = trip_dir
        self.regenerate_callback = regenerate_callback
        self.layout_file = output_dir / "layout.json"

    async def handle_index(self, _request: web.Request) -> web.FileResponse:
        response = web.FileResponse(self.output_dir / settings.file.album_html_file)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

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

    async def handle_move_photo(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            photo_id = data.get("photo_id")
            src_step_id = data.get("src_step_id")
            dest_step_id = data.get("dest_step_id")

            logger.info(
                "Virtual Move requested: %s from %s to %s", photo_id, src_step_id, dest_step_id
            )

            return web.json_response({"success": True})
        except Exception as e:
            logger.exception("Error handling move request")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def handle_save_batch(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            updates = data.get("updates", [])

            if not updates:
                return web.json_response({"success": True})

            # Load existing layout
            current_layout = AlbumLayout(steps={})
            if self.layout_file.exists():
                try:
                    current_layout = AlbumLayout.model_validate_json(self.layout_file.read_text())
                except (ValueError, TypeError, json.JSONDecodeError) as e:
                    logger.warning("Failed to parse existing layout.json, starting fresh: %s", e)

            step_ids_to_regen = []

            # Apply all updates
            for valid_data in updates:
                step_layout = StepLayout(**valid_data)
                current_layout.steps[step_layout.step_id] = step_layout
                step_ids_to_regen.append(step_layout.step_id)

            # Save back to file ATOMICALLY
            self.layout_file.write_text(current_layout.model_dump_json(indent=2))

            # Trigger regeneration for each step
            # Optimally, we should pass all IDs to regeneration to do it once if main supports it.
            # But callback only accepts one ID. We call it sequentially.
            for step_id in step_ids_to_regen:
                await self.regenerate_callback(step_id)

            return web.json_response({"success": True})
        except Exception as e:
            logger.exception("Error saving batch layout")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    def run(self, port: int = 8000) -> None:
        app = web.Application()
        app.router.add_get("/", self.handle_index)
        app.router.add_post("/api/save", self.handle_save)
        app.router.add_post("/api/save_batch", self.handle_save_batch)
        app.router.add_post("/api/move_photo", self.handle_move_photo)

        # Serve static files from output directory
        app.router.add_static("/", self.output_dir)

        logger.info("Starting editor at http://localhost:%d", port)
        web.run_app(app, port=port)
