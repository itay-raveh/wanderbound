"""Home page layout."""

from nicegui import ui

from psagen.core.logger import get_logger
from psagen.logic.generator import try_get_generator_args
from psagen.ui.components.preview import create_preview_panel, generate, show_album_frame
from psagen.ui.components.sidebar import create_setup_panel
from psagen.ui.components.terminal import FileCompatXTerm
from psagen.ui.theme import THEME_VARS

logger = get_logger(__name__)


@ui.page("/")
async def home_page() -> None:
    """Attributes for the main index page."""
    try:
        # Inject design system CSS
        ui.add_head_html('<link rel="stylesheet" href="/static/style.css">')
        ui.add_head_html(f"<style>{THEME_VARS}</style>")

        # Shared state
        album_frame: ui.element | None = None
        terminal: FileCompatXTerm | None = None
        layout_toolbar: ui.row | None = None

        async def do_generate() -> None:
            nonlocal album_frame, terminal, layout_toolbar
            if terminal and album_frame and layout_toolbar:
                await generate(terminal, album_frame, layout_toolbar)

        with ui.row(wrap=False).classes("w-full h-screen p-4 pb-8 gap-4 no-scroll"):
            # Left: Setup Panel
            with ui.card().classes("h-full p-4 scroll-y").style("width: 340px; flex-shrink: 0"):
                create_setup_panel(do_generate)

            # Right: Preview Panel
            with ui.card().classes("flex-grow h-full p-4 flex flex-col no-scroll"):
                album_frame, terminal, layout_toolbar = await create_preview_panel()

        if try_get_generator_args() is not None and album_frame and layout_toolbar:
            await show_album_frame(album_frame, layout_toolbar)

    except Exception as e:
        logger.exception("Error in home_page")
        ui.label(f"Error loading page: {e}").classes("text-red-500 font-bold")
