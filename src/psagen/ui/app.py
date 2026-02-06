"""Main Application configuration."""

import asyncio

from nicegui import app, ui

from psagen.api.router import api_router
from psagen.core.logger import get_logger
from psagen.core.session import get_session_id, start_cleanup_task
from psagen.core.settings import settings

logger = get_logger(__name__)

# Background cleanup
_background_tasks: set[asyncio.Task[None]] = set()


def configure_app() -> None:
    """Configure the NiceGUI application (mounts, hooks, etc)."""
    # Mount Static Files
    app.add_static_files("/static", settings.static_dir)
    app.mount("/api", api_router)

    # Startup Tasks
    async def _start_background_tasks() -> None:
        if not _background_tasks:  # Only start once
            task = asyncio.create_task(start_cleanup_task())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)

    app.on_startup(_start_background_tasks)

    # Exception Handling
    def handle_exception(e: Exception) -> None:
        sess_id = get_session_id()
        logger.exception("Global error in session %s", sess_id, exc_info=e)

        with ui.dialog() as d, ui.card().classes("border-red-500 border-2"):
            with ui.row().classes("items-center gap-2 text-red-400"):
                ui.icon("error", size="md")
                ui.label("An unexpected error occurred").classes("text-lg font-bold")

            ui.separator().classes("my-2 bg-red-500 opacity-20")
            ui.label(str(e)).classes("my-2 font-mono text-sm bg-black/20 p-2 rounded")

            with ui.row().classes("w-full justify-between items-center mt-2"):
                ui.label(f"Session: {sess_id[:8]}...").classes("text-xs text-gray-500")
                ui.button("Close", on_click=d.close).props("flat color=white")
        d.open()

    app.on_exception(handle_exception)
