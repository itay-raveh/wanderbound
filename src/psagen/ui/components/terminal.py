"""Terminal component wrapper."""

from typing import IO

from nicegui import ui

from psagen.ui.theme import COLORS

# Terminal styling
TERMINAL_THEME = {
    "foreground": COLORS["text"],
    "background": COLORS["bg_card"],
    "selection": "#97979b33",
    "cursor": COLORS["accent"],
}


# noinspection PyAbstractClass
class FileCompatXTerm(ui.xterm, IO[str]):  # pyright: ignore[reportIncompatibleMethodOverride]
    """XTerm that implements file protocol for IO compatibility."""

    def flush(self) -> None:
        self.update()
