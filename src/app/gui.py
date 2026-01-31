"""GUI entry point for the album generator using NiceGUI."""

# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportAny=false, reportExplicitAny=false

from __future__ import annotations

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
    from pathlib import Path

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


def create_args_form() -> None:
    # Use GeneratorArgs fields to build Form
    for name, field in GeneratorArgs.model_fields.items():
        label = name.replace("_", " ").title()
        with ui.row().classes("w-full items-center"):
            # Boolean -> Checkbox
            if field.annotation is bool:
                inp = ui.checkbox(label)

            # Path -> File Picker
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
                app.storage.general, name
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


def _path_to_mount(path: Path) -> str:
    """Convert a file path to a URL-friendly mount path."""
    # On Windows, as_posix() returns 'C:/...', which we need to prepend with '/'
    # to make it a valid URL path '/C:/...'. On Linux, it's already '/home/...'.
    s = path.absolute().as_posix()
    return s if s.startswith("/") else "/" + s


async def show_album_frame(album_frame: ui.element, args: GeneratorArgs) -> None:
    # Ensure static files are served
    app.add_static_files(_path_to_mount(args.output), args.output)
    app.add_static_files(_path_to_mount(args.trip), args.trip)

    # Show album
    album_frame.visible = True

    # Refresh iframe
    # Use a unique timestamp to force reload if the file changed
    src = f"{_path_to_mount(args.output / 'album.html')}?t={time()}"
    await ui.run_javascript(f"getHtmlElement({album_frame.id}).src='{src}';")


async def generate(terminal: FileCompatXTerm, album_frame: ui.element) -> None:
    # Reset UI
    await terminal.run_terminal_method("clear")
    album_frame.visible = False

    # Validate inputs from storage
    args = get_generator_args()

    if args.no_cache:
        clear_cache()
        logger.warning("Cleared cache")

    # Load and generate
    service = await get_album_service(args)
    await service.generate()

    await show_album_frame(album_frame, service.args)


@ui.page("/")
async def index_page() -> None:
    ui.on_exception(lambda exc: logger.exception("Error:", exc_info=exc))

    with ui.row(wrap=False).classes("w-full h-[95vh]"):
        with ui.column().classes("w-1/3 h-full gap-2") as form:
            create_args_form()

        with ui.column().classes("w-2/3 h-full"):
            album_frame, terminal = await create_display()

        with form:
            (
                ui.button(
                    "Generate Album",
                    color="primary",
                    icon="play_arrow",
                    on_click=lambda: generate(terminal, album_frame),
                )
                .classes("w-full mt-4")
                .bind_enabled_from(
                    app.storage, "general", lambda _: (try_get_generator_args() is not None)
                )
            )

    if args := try_get_generator_args():
        await show_album_frame(album_frame, args)


app.mount("/api", api_router)

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="Polarsteps Album Generator",
        dark=True,
        reload=not getattr(sys, "frozen", False),
        uvicorn_reload_dirs="src,static",
    )
