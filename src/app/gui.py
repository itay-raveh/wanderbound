"""GUI entry point for the album generator using NiceGUI."""

# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportAny=false, reportExplicitAny=false

from __future__ import annotations

import sys

from pathlib import Path
from time import time
import tkinter as tk
from functools import partial
from tkinter import filedialog
from typing import IO, TYPE_CHECKING, Any

from nicegui import app, run, ui
from pydantic import ConfigDict, TypeAdapter, ValidationError
from rich.console import Console

from src.app.api import api_router
from src.app.engine import run_generation_task
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


# noinspection PyAbstractClass
class FileCompatXTerm(
    ui.xterm, IO[str]
):  # pyright: ignore[reportIncompatibleMethodOverride]
    def flush(self) -> None:
        self.update()


def _make_field_validator(field_info: FieldInfo) -> ValidationFunction:
    """Create a validator for a NiceGUI input based on Pydantic types."""

    def validator(value: Any) -> str | None:
        try:
            TypeAdapter(
                field_info.annotation, config=ConfigDict(arbitrary_types_allowed=True)
            ).validate_python(value)
        except ValidationError as e:
            # Return the first error message, stripping the "Value error, " prefix if present
            msg = e.errors()[0]["msg"]
            return msg.replace("Value error, ", "")

    return validator


def _pick_file_or_folder(label: str, is_dir: bool, initial: str) -> str | None:
    # Create a hidden root window
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    root.attributes("-topmost", True)  # Make the dialog appear on top

    try:
        if is_dir:
            path = filedialog.askdirectory(
                title=label, mustexist=True, parent=root, initialdir=initial
            )
        else:
            path = filedialog.askopenfilename(
                title=label, parent=root, initialdir=initial
            )
    finally:
        root.destroy()

    return str(path) if path else None


def _make_file_picker_handler(
    inp: ui.input, field: FieldInfo
) -> Handler[ClickEventArguments]:
    async def handler() -> None:
        is_dir = "path_type='dir'" in str(field)
        # Run in a separate thread to not block the GUI event loop
        path = await run.io_bound(
            partial(_pick_file_or_folder, f"Choose {inp.label}", is_dir, inp.value)
        )

        if path:
            inp.set_value(path)

    return handler


def create_form() -> ui.button:
    # Use GeneratorArgs fields to build Form
    with ui.column().classes("w-full p-4 gap-2"):
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

                inp.classes("flex-grow").props(
                    f'dense hint="{field.description or ""}"'
                ).bind_value(app.storage.general, name)
        return ui.button("Generate Album", color="primary", icon="play_arrow").classes(
            "w-full mt-4"
        )


def _path_to_mount(path: Path) -> str:
    s = path.absolute().as_posix()
    return s if s.startswith("/") else "/" + s


async def generate(
    terminal: FileCompatXTerm,
    album_frame: ui.element,
) -> None:
    # Reset UI
    await terminal.run_terminal_method("clear")
    terminal.visible = True
    album_frame.visible = False

    try:
        args = GeneratorArgs.model_validate(
            {k: (None if v == "" else v) for k, v in app.storage.general.items()}
        )
    except ValidationError as e:
        err = e.errors()[0]
        logger.error("%s: %s", err["input"], err["msg"])
        return

    try:
        await run_generation_task(args)
    except Exception:
        logger.exception("Generation Error:")
        return

    app.add_static_files(_path_to_mount(args.output), args.output)
    app.add_static_files(_path_to_mount(args.trip), args.trip)

    album_frame.visible = True
    terminal.visible = False
    # Refresh iframe
    await ui.run_javascript(
        f"getHtmlElement({album_frame.id}).src='{_path_to_mount(args.output / 'album.html')}?t={time()}';"
    )


@ui.page("/")
async def index_page() -> None:
    with ui.row(wrap=False).classes("size-full"):
        with ui.column().classes("w-1/3 h-full"):
            generate_btn = create_form()

        with ui.column().classes("w-2/3 h-[90vh]"):
            album_frame = ui.element("iframe").classes("size-full").style("zoom: 70%")
            album_frame.visible = False

            terminal = FileCompatXTerm(
                options={
                    "theme": TERMINAL_THEME,
                    "fontFamily": TERMINAL_FONT_FAMILY,
                    "disableStdin": True,
                    "cursorBlink": False,
                    "convertEol": True,
                }
            ).classes("size-full")

            if terminal.visible:
                await terminal.fit()

        generate_btn.on_click(lambda: generate(terminal, album_frame))

    set_console(
        Console(
            file=TeeIO(sys.stdout, terminal),
            force_terminal=True,
            width=await terminal.get_columns(),
            height=await terminal.get_rows(),
        )
    )


app.mount("/api", api_router)

if __name__ in {"__main__", "__mp_main__"}:
    # Disable reload when frozen (packaged)
    reload_app = not getattr(sys, "frozen", False)
    ui.run(title="Polarsteps Album Generator", dark=True, reload=reload_app)
