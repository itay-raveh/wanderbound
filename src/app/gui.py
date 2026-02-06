"""GUI entry point for the album generator using NiceGUI."""

# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportAny=false, reportExplicitAny=false

from __future__ import annotations

import asyncio
import sys
from time import time
from typing import IO, TYPE_CHECKING, Any

from nicegui import app, run, ui
from pydantic import ConfigDict, TypeAdapter, ValidationError
from rich.console import Console

from src.app.api import api_router
from src.app.engine import (
    get_album_service,
    get_generator_args,
    try_get_generator_args,
)
from src.core.cache import clear_cache
from src.core.logger import TeeIO, get_logger, set_console
from src.models.args import GeneratorArgs

if TYPE_CHECKING:
    from nicegui.elements.mixins.validation_element import ValidationFunction
    from nicegui.events import ClickEventArguments, Handler
    from pydantic.fields import FieldInfo

logger = get_logger(__name__)

TERMINAL_FONT_FAMILY = '"Cascadia Code", Menlo, monospace'
TERMINAL_THEME = {
    "foreground": "#eff0eb",
    "background": "#282a36",
    "selection": "#97979b33",
    "black": "#282a36",
    "brightBlack": "#686868",
    "red": "#ff5c57",
    "brightRed": "#ff5c57",
    "green": "#5af78e",
    "brightGreen": "#5af78e",
    "yellow": "#f3f99d",
    "brightYellow": "#f3f99d",
    "blue": "#57c7ff",
    "brightBlue": "#57c7ff",
    "magenta": "#ff6ac1",
    "brightMagenta": "#ff6ac1",
    "cyan": "#9aedfe",
    "brightCyan": "#9aedfe",
    "white": "#f1f1f0",
    "brightWhite": "#eff0eb",
}


def _make_field_validator(field_info: FieldInfo) -> ValidationFunction:
    """Create a validator for a NiceGUI input based on Pydantic types."""

    def validator(value: Any) -> str | None:
        try:
            TypeAdapter(
                field_info.annotation, config=ConfigDict(arbitrary_types_allowed=True)
            ).validate_python(value or None)
        except ValidationError as e:
            # Return the first error message, stripping the "Value error, " prefix if present
            msg = e.errors()[0]["msg"]
            return msg.replace("Value error, ", "")

    return validator


def _pick_file_or_folder(title: str, initial: str, *, is_dir: bool) -> str | None:
    import tkinter as tk  # noqa: PLC0415
    from tkinter import filedialog  # noqa: PLC0415

    # Create a hidden root window
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost")

    try:
        if is_dir:
            path = filedialog.askdirectory(
                title=title, mustexist=True, parent=root, initialdir=initial
            )
        else:
            path = filedialog.askopenfilename(title=title, parent=root, initialdir=initial)
    finally:
        root.destroy()

    return str(path) if path else None


def _make_file_picker_handler(inp: ui.input, field: FieldInfo) -> Handler[ClickEventArguments]:
    async def handler() -> None:
        is_dir = "path_type='dir'" in str(field)
        # Run in a separate thread to not block the GUI event loop
        path = await run.io_bound(
            _pick_file_or_folder, f"Choose {inp.label}", inp.value, is_dir=is_dir
        )

        if path:
            inp.set_value(path)

    return handler


# Fields that are auto-managed by session (not shown in form)
_HIDDEN_FIELDS = {"trip", "output"}


def create_args_form() -> None:
    """Create the upload/trip selector and form fields bound to app.storage.user."""
    from src.core.session import extract_zip_upload, get_output_dir, get_trips_dir  # noqa: PLC0415

    # Track available trips in user storage
    trips_key = "_available_trips"
    selected_trip_key = "_selected_trip"

    # Placeholder for trip_select widget (created after handler definition)
    trip_select: ui.select | None = None

    async def handle_upload(event: Any) -> None:
        """Handle zip file upload and populate trip selector."""
        nonlocal trip_select

        # Show loading notification
        loading_notify = ui.notification("Extracting zip file...", type="ongoing", spinner=True)

        try:
            trips = await extract_zip_upload(event)
            app.storage.user[trips_key] = trips
            if trip_select:
                trip_select.options = trips
                trip_select.set_visibility(bool(trips))
                if trips:
                    app.storage.user[selected_trip_key] = trips[0]
                    trip_select.value = trips[0]
                    _update_trip_paths(trips[0])

            loading_notify.dismiss()
            ui.notify(f"Extracted {len(trips)} trip(s)", type="positive")
        except ValueError as e:
            loading_notify.dismiss()
            ui.notify(str(e), type="negative")

    def _update_trip_paths(trip_slug: str) -> None:
        """Update trip and output paths in storage based on selected trip."""
        trips_dir = get_trips_dir()
        output_dir = get_output_dir()
        app.storage.user["trip"] = str(trips_dir / trip_slug)
        app.storage.user["output"] = str(output_dir)

    def on_trip_change(e: Any) -> None:
        """Handle trip selection change."""
        if e.value:
            app.storage.user[selected_trip_key] = e.value
            _update_trip_paths(e.value)

    # Zip Upload Section
    with ui.card().classes("w-full"):
        ui.label("Upload Polarsteps Export").classes("text-lg font-bold")
        ui.upload(
            label="Upload .zip file",
            on_upload=handle_upload,
            auto_upload=True,
        ).props("accept=.zip").classes("w-full")

        # Trip Selector (hidden until upload completes)
        trip_select = (
            ui.select(
                options=[],
                label="Select Trip",
                on_change=on_trip_change,
            )
            .classes("w-full")
            .bind_value(app.storage.user, selected_trip_key)
        )
        trip_select.set_visibility(False)

    # Divider
    ui.separator()
    ui.label("Album Settings").classes("text-lg font-bold")

    # Other fields from GeneratorArgs
    for name, field in GeneratorArgs.model_fields.items():
        if name in _HIDDEN_FIELDS:
            continue

        label = name.replace("_", " ").title()
        with ui.row().classes("w-full items-center"):
            # Boolean -> Checkbox
            if field.annotation is bool:
                inp = ui.checkbox(label)

            # Path -> File Picker (for cover/back_cover only now)
            elif "Path" in str(field.annotation):
                with ui.row().classes("w-full"):
                    inp = ui.input(
                        label,
                        validation=_make_field_validator(field),
                    ).props("disable")
                    ui.button(
                        icon="folder",
                        on_click=_make_file_picker_handler(inp, field),
                    )

            # SliceList or str -> Input
            else:
                inp = ui.input(
                    label,
                    validation=_make_field_validator(field),
                ).props("outlined")

            inp.classes("flex-grow").props(f'dense hint="{field.description or ""}"').bind_value(
                app.storage.user, name
            )


# noinspection PyAbstractClass
class FileCompatXTerm(ui.xterm, IO[str]):  # pyright: ignore[reportIncompatibleMethodOverride]
    def flush(self) -> None:
        self.update()


async def create_display() -> tuple[ui.element, FileCompatXTerm]:
    # Album iframe
    album_frame = ui.element("iframe").classes("size-full").style("zoom: 70%")
    album_frame.visible = False

    # Terminal simulator, visible only wen the album isn't
    terminal = (
        FileCompatXTerm(
            options={
                "theme": TERMINAL_THEME,
                "fontFamily": TERMINAL_FONT_FAMILY,
                "disableStdin": True,
                "cursorBlink": False,
                "convertEol": True,
            }
        )
        .classes("size-full")
        .bind_visibility_from(album_frame, "visible", value=False)
    )

    await ui.context.client.connected()
    await terminal.fit()
    width = await terminal.get_columns()
    height = await terminal.get_rows()

    set_console(
        Console(
            file=TeeIO(sys.stdout, terminal),
            force_terminal=True,
            width=width,
            height=height,
        )
    )

    return album_frame, terminal


async def show_album_frame(album_frame: ui.element) -> None:
    """Display the generated album in an iframe."""
    from src.core.session import get_session_id  # noqa: PLC0415

    # Show album
    album_frame.visible = True

    # Build session-based album URL
    session_id = get_session_id()
    album_url = f"/api/session/{session_id}/assets/output/album.html?t={time()}"

    # Refresh iframe with session URL
    await ui.run_javascript(f"getHtmlElement({album_frame.id}).src='{album_url}';")


async def download_layout() -> None:
    """Download the current layout.json file."""
    args = try_get_generator_args()
    if args is None:
        ui.notify("No album generated yet", type="warning")
        return

    layout_path = args.output / "layout.json"
    if not layout_path.exists():
        ui.notify("No layout file found. Generate an album first.", type="warning")
        return

    ui.download(layout_path.read_bytes(), "layout.json")
    ui.notify("Layout downloaded", type="positive")


async def on_layout_upload(event: Any, dialog: ui.dialog) -> None:
    """Handle uploaded layout.json file with validation."""
    import json  # noqa: PLC0415

    from src.models.layout import AlbumLayout  # noqa: PLC0415

    args = try_get_generator_args()
    if args is None:
        ui.notify("No album configured. Set up your trip first.", type="warning")
        dialog.close()
        return

    try:
        content = event.content.read()
        layout_data = json.loads(content)

        # Validate layout structure
        try:
            AlbumLayout.model_validate(layout_data)
        except (ValueError, TypeError) as e:
            ui.notify(f"Invalid layout format: {e}", type="negative")
            dialog.close()
            return

        # Validate step IDs match current trip (if trip.json exists)
        trip_json = args.trip / "trip.json"
        if trip_json.exists():
            trip_data = json.loads(trip_json.read_text())
            trip_step_ids = {step["id"] for step in trip_data.get("all_steps", [])}
            layout_step_ids = {s["id"] for s in layout_data.get("step_layouts", [])}

            unknown_ids = layout_step_ids - trip_step_ids
            if unknown_ids:
                ui.notify(
                    f"Layout contains step IDs not in current trip: {unknown_ids}",
                    type="warning",
                )

        # Write to output directory
        layout_path = args.output / "layout.json"
        layout_path.parent.mkdir(parents=True, exist_ok=True)
        layout_path.write_text(json.dumps(layout_data, indent=2))

        ui.notify("Layout restored! Regenerate to apply.", type="positive")
    except (json.JSONDecodeError, OSError) as e:
        ui.notify(f"Invalid layout file: {e}", type="negative")
    finally:
        dialog.close()


async def generate(terminal: FileCompatXTerm, album_frame: ui.element) -> None:
    # Reset UI
    await terminal.run_terminal_method("clear")
    album_frame.visible = False

    # Create progress dialog
    with ui.dialog() as progress_dialog, ui.card().classes("w-96"):
        ui.label("Generating Album").classes("text-lg font-bold")
        progress_bar = ui.linear_progress(show_value=False).props("indeterminate")
        status_label = ui.label("Starting...")

    progress_dialog.open()

    try:
        # Validate inputs from storage
        args = get_generator_args()

        if args.no_cache:
            clear_cache()
            logger.warning("Cleared cache")

        status_label.text = "Loading trip data..."
        await asyncio.sleep(0.1)  # Allow UI update

        # Load and generate
        service = await get_album_service(args)

        status_label.text = "Fetching weather, maps, and flags..."
        await asyncio.sleep(0.1)

        await service.generate()

        status_label.text = "Complete!"
        progress_bar.props(remove="indeterminate")
        progress_bar.value = 1.0
        await asyncio.sleep(0.5)

    finally:
        progress_dialog.close()

    await show_album_frame(album_frame)


@ui.page("/")
async def index_page() -> None:
    ui.on_exception(lambda exc: logger.exception("Error:", exc_info=exc))

    with ui.row(wrap=False).classes("w-full h-[95vh]"):
        with ui.column().classes("w-1/3 h-full gap-2"):
            create_args_form()
            generate_btn = ui.button(
                "Generate Album",
                color="primary",
                icon="play_arrow",
                on_click=lambda: generate(terminal, album_frame),
            ).classes("w-full mt-4")
            generate_btn.bind_enabled_from(
                app.storage.user, lambda _: try_get_generator_args() is not None
            )

            # Layout export/import
            with ui.row().classes("w-full gap-2"):
                ui.button(
                    "Download Layout",
                    icon="download",
                    on_click=download_layout,
                ).classes("flex-1").props("outline")
                ui.button(
                    "Upload Layout",
                    icon="upload",
                    on_click=lambda: upload_layout_dialog.open(),
                ).classes("flex-1").props("outline")

            # Hidden upload dialog
            with ui.dialog() as upload_layout_dialog, ui.card().classes("w-96"):
                ui.label("Upload Layout").classes("text-lg font-bold")
                ui.label("Select a layout.json file to restore your edits.")
                ui.upload(
                    label="layout.json",
                    auto_upload=True,
                    on_upload=lambda e: on_layout_upload(e, upload_layout_dialog),
                ).props("accept=.json")

        with ui.column().classes("w-2/3 h-full"):
            album_frame, terminal = await create_display()

    if try_get_generator_args() is not None:
        await show_album_frame(album_frame)


# Register background task for session cleanup
_background_tasks: set[asyncio.Task[None]] = set()


@app.on_startup
async def _start_background_tasks() -> None:
    """Start background tasks when the application starts."""
    from src.core.session import start_cleanup_task  # noqa: PLC0415

    task = asyncio.create_task(start_cleanup_task())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


app.mount("/api", api_router)

if __name__ in {"__main__", "__mp_main__"}:
    import os
    import secrets

    # Use environment variable for production, or generate for development
    storage_secret = os.environ.get("NICEGUI_STORAGE_SECRET", secrets.token_hex(32))

    ui.run(
        title="Polarsteps Album Generator",
        dark=True,
        reload=True,
        uvicorn_reload_dirs="src,static",
        storage_secret=storage_secret,
    )
