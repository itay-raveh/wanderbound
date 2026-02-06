"""Preview component with Album/Terminal switch."""

import asyncio
import json
import sys
from time import time
from typing import Any

from nicegui import ui
from rich.console import Console

from psagen.core.cache import clear_cache
from psagen.core.logger import TeeIO, get_logger, set_console
from psagen.core.session import get_session_id
from psagen.logic.generator import get_album_service, get_generator_args, try_get_generator_args
from psagen.models.layout import AlbumLayout
from psagen.ui.components.terminal import TERMINAL_THEME, FileCompatXTerm
from psagen.ui.theme import COLORS

logger = get_logger(__name__)


def create_layout_toolbar() -> ui.row:
    """Create the layout management toolbar."""

    async def download_layout() -> None:
        args = try_get_generator_args()
        if not args:
            ui.notify("No album generated yet", type="warning")
            return
        layout_path = args.output / "layout.json"
        if not layout_path.exists():
            ui.notify("No layout file found", type="warning")
            return
        ui.download(layout_path.read_bytes(), "layout.json")
        ui.notify("Layout downloaded", type="positive")

    async def on_layout_upload(event: Any, dialog: ui.dialog) -> None:
        args = try_get_generator_args()
        if not args:
            dialog.close()
            return

        try:
            layout_data = json.loads(event.content.read())
            AlbumLayout.model_validate(layout_data)
            layout_path = args.output / "layout.json"
            layout_path.parent.mkdir(parents=True, exist_ok=True)
            layout_path.write_text(json.dumps(layout_data, indent=2))
            ui.notify("Layout restored! Regenerate to apply.", type="positive")
        except (ValueError, TypeError) as e:
            ui.notify(f"Invalid layout: {e}", type="negative")
        finally:
            dialog.close()

    with (
        ui.row()
        .classes("w-full justify-between items-center px-4 py-2 rounded-lg")
        .style(f"background: {COLORS['bg_input']}") as toolbar
    ):
        ui.label("✓ Layout saved").classes("text-sm").style(f"color: {COLORS['success']}")

        with ui.row().classes("gap-2"):
            ui.button("Export", icon="download", on_click=download_layout).props(
                "flat dense size=sm"
            )

            with ui.dialog() as upload_dialog, ui.card().classes("w-80"):
                ui.label("Import Layout").classes("font-semibold")
                ui.label("Upload a layout.json to restore previous edits.").classes(
                    "text-sm text-gray-400"
                )
                ui.upload(
                    label="layout.json",
                    auto_upload=True,
                    on_upload=lambda e: on_layout_upload(e, upload_dialog),
                ).props("accept=.json flat")

            ui.button("Import", icon="upload", on_click=upload_dialog.open).props(
                "flat dense size=sm"
            )

            with ui.element("span").tooltip(
                "Your edits are saved automatically. Export to backup, Import to restore."
            ):
                ui.icon("help_outline", size="xs").classes("cursor-help text-gray-400")

    toolbar.visible = False
    return toolbar


async def create_preview_panel() -> tuple[ui.element, FileCompatXTerm, ui.row]:
    """Create the preview panel with album iframe & terminal."""
    album_frame = ui.element("iframe").classes("w-full flex-grow rounded-lg").style("min-height: 0")
    album_frame.visible = False

    terminal = (
        FileCompatXTerm(
            options={
                "theme": TERMINAL_THEME,
                "fontFamily": "'JetBrains Mono', 'Cascadia Code', monospace",
                "fontSize": 13,
                "disableStdin": True,
                "cursorBlink": False,
                "convertEol": True,
            }
        )
        .classes("w-full flex-grow rounded-lg")
        .style("min-height: 0")
        .bind_visibility_from(album_frame, "visible", value=False)
    )

    await ui.context.client.connected()
    await terminal.fit()
    width = await terminal.get_columns()
    height = await terminal.get_rows()

    # Setup global console redirection to this terminal
    tee = TeeIO(sys.stdout, terminal)
    console = Console(file=tee, width=width or 120, height=height or 40, force_terminal=True)
    set_console(console)

    layout_toolbar = create_layout_toolbar()
    return album_frame, terminal, layout_toolbar


async def show_album_frame(album_frame: ui.element, layout_toolbar: ui.row) -> None:
    """Display the generated album."""
    album_frame.visible = True
    layout_toolbar.visible = True
    session_id = get_session_id()
    album_url = f"/api/session/{session_id}/assets/output/album.html?t={time()}"
    await ui.run_javascript(f"getHtmlElement({album_frame.id}).src='{album_url}';")


async def generate(
    terminal: FileCompatXTerm, album_frame: ui.element, layout_toolbar: ui.row
) -> None:
    """Run album generation with progress dialog."""
    await terminal.run_terminal_method("clear")
    album_frame.visible = False
    layout_toolbar.visible = False

    with ui.dialog() as progress_dialog, ui.card().classes("w-80 items-center p-6"):
        ui.label("Generating Album...").classes("text-lg font-semibold")
        ui.linear_progress(show_value=False).props("indeterminate").classes("w-full mt-4")
        status_label = ui.label("Starting...").classes("text-sm text-gray-400 mt-2")

    progress_dialog.open()

    try:
        args = get_generator_args()
        if args.no_cache:
            clear_cache()

        status_label.text = "Loading trip data..."
        await asyncio.sleep(0.1)
        service = await get_album_service(args)

        status_label.text = "Fetching weather, maps, flags..."
        await asyncio.sleep(0.1)
        await service.generate()

        status_label.text = "Complete!"
        await asyncio.sleep(0.5)
    finally:
        progress_dialog.close()

    await show_album_frame(album_frame, layout_toolbar)
