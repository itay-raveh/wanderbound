"""GUI entry point for the album generator using NiceGUI."""
# ruff: noqa: SLF001
# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportAny=false, reportExplicitAny=false

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from nicegui import app, background_tasks, ui
from rich.console import Console

from src.app.args import Args
from src.app.file_picker import FilePicker
from src.app.main import setup_server
from src.core.logger import get_logger, set_console
from src.core.settings import settings

if TYPE_CHECKING:
    from collections.abc import Callable

    from nicegui.elements.mixins.validation_element import ValidationFunction
    from nicegui.events import GenericEventArguments


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
class FileCompatXTerm(ui.xterm, IO[str]):  # pyright: ignore[reportIncompatibleMethodOverride]
    def flush(self) -> None:
        self.update()


def _make_field_validator(cls: Callable[[Any], Any], *, required: bool) -> ValidationFunction:
    def validator(value: Any) -> str | None:
        if not value:
            return "Required" if required else None

        try:
            cls(value)
        except (TypeError, ValueError) as e:
            return str(e)

    return validator


def create_form_from_args() -> ui.button:
    inputs: list[ui.input | ui.checkbox] = []
    # Layout the form
    with ui.column().classes("w-full p-4 gap-2"):
        for action in Args(underscores_to_dashes=True)._actions:
            if isinstance(action, argparse._HelpAction):
                continue

            label = action.dest.replace("_", " ").title()

            with ui.row().classes("w-full items-center"):
                # noinspection PyTypeChecker
                # bool -> checkbox
                if isinstance(action, argparse._StoreTrueAction):
                    inp = ui.checkbox(label)

                # Path -> file picker
                elif issubclass(action.type, Path):  # pyright: ignore[reportArgumentType]

                    async def pick(event: GenericEventArguments) -> None:
                        # TODO(itay): ~
                        # noinspection PyUnresolvedReferences
                        event.sender.set_value(await FilePicker("."))  # pyright: ignore[reportAttributeAccessIssue]

                    with ui.row().classes("w-full"):
                        inp = (
                            ui.input(
                                label,
                                value=action.default,
                                validation=_make_field_validator(
                                    action.type, required=action.required
                                ),
                            )
                            .props("readonly dirty")
                            .on("click", pick)
                        )

                        with inp:
                            ui.icon("folder").classes("h-full")

                # else -> text input
                else:
                    inp = ui.input(
                        label,
                        value=action.default,
                        validation=_make_field_validator(action.type, required=action.required),
                    )

                inp.props("outlined dense").classes("flex-grow").bind_value(
                    app.storage.general, action.dest
                )

                if action.help:
                    hint = re.sub(r"^\(.*?\)", "", action.help)
                    inp.props(f"hint='{hint}'")

                inputs.append(inp)

        return (
            ui.button("Generate Album", color="primary", icon="play_arrow")
            .classes("w-full mt-4")
            .bind_enabled_from(
                locals(),
                "inputs",
                lambda inputs_: all(
                    input_.validate() for input_ in inputs_ if hasattr(input_, "validate")
                ),
            )
        )


async def run_generator_action(
    values: dict[str, Any],
    terminal: ui.xterm,
    album_frame: ui.element,
) -> None:
    """Construct Args and run the generator."""
    # Reset state
    await terminal.run_terminal_method("clear")
    terminal.visible = True
    album_frame.visible = False

    # 1. Simulate CLI arguments
    cli_args: list[str] = []
    for key, value in values.items():
        arg = "--" + key.replace("_", "-")
        if isinstance(value, bool):
            if value:
                cli_args.append(arg)
        elif value:
            cli_args.extend([arg, str(value)])

    try:
        parsed_args = Args(underscores_to_dashes=True, exit_on_error=False).parse_args(cli_args)
    except (ValueError, argparse.ArgumentError) as e:
        logger.error("Argument error: %s", str(e))
        return

    # 2. Setup Server
    # noinspection PyBroadException
    try:
        server = await setup_server(parsed_args)
    except Exception:
        logger.exception("Generation error:")
        return

    # 3. Start the blocking server in a separate thread
    background_tasks.create_lazy(server.run(), name="Editor")

    # 4. Success! Show Album
    album_frame.visible = True
    terminal.visible = False
    await ui.run_javascript(f"var frame = getHtmlElement({album_frame.id}); frame.src = frame.src;")
    album_frame.update()


@ui.page("/")
async def index_page() -> None:
    with ui.row(wrap=False).classes("size-full") as container:
        with ui.column().classes("w-1/3 h-full"):
            generate_btn = create_form_from_args()

        with ui.column().classes("w-2/3 h-[90vh]"):
            album_frame = (
                ui.element("iframe")
                .classes("size-full")
                .props(
                    f'sandbox="allow-same-origin allow-scripts allow-popups allow-forms" src="http://localhost:{settings.editor_port}"'
                )
                .style("zoom: 70%")
            )
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

            await terminal.fit()

        generate_btn.on_click(
            lambda: run_generator_action(app.storage.general, terminal, album_frame)
        )

        set_console(
            Console(
                file=terminal,
                force_terminal=True,
                width=await terminal.get_columns(),
                height=await terminal.get_rows(),
            )
        )

    class NotifyErrorHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            with container:
                ui.notify(
                    self.format(record),
                    close_button=True,
                    multi_line=True,
                    type="warning" if record.levelno == logging.WARNING else "negative",
                )

    handler = NotifyErrorHandler()
    handler.setLevel(logging.WARNING)
    logger.root.addHandler(handler)


def main() -> None:
    ui.run(title="Polarsteps Album Generator", dark=True)


if __name__ in {"__main__", "__mp_main__"}:
    main()
