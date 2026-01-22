"""Derived from https://github.com/zauberzeug/nicegui/blob/main/examples/local_file_picker/local_file_picker.py."""

# pyright: basic

import platform
from pathlib import Path

from nicegui import events, ui

if platform.system() == "Windows":
    import win32api  # pyright: ignore[reportMissingModuleSource]


class FilePicker(ui.dialog):
    def __init__(
        self,
        directory: str,
        *,
        upper_limit: str | None = None,
        show_hidden_files: bool = False,
    ) -> None:
        """Local File Picker.

        This is a simple file picker that allows you to select
         a file from the local filesystem where NiceGUI is running.

        :param directory: The directory to start in.
        :param upper_limit: The directory to stop at (None: no limit).
        :param show_hidden_files: Whether to show hidden files.
        """
        super().__init__()

        self.path = Path(directory).expanduser()
        if upper_limit is None:
            self.upper_limit = None
        else:
            self.upper_limit = Path(upper_limit).expanduser()
        self.show_hidden_files = show_hidden_files

        with self, ui.card().classes("w-full h-8/10"):
            self.add_drives_toggle()
            self.grid = (
                ui.aggrid(
                    {
                        "columnDefs": [{"field": "name", "headerName": "File"}],
                        "rowSelection": {
                            "mode": "singleRow",
                            "checkboxes": False,
                            "enableClickSelection": True,
                        },
                    },
                    html_columns=[0],
                )
                .classes("w-full h-full")
                .on("cellDoubleClicked", self.handle_double_click)
            )
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=self.close).props("outline")
                ui.button("Ok", on_click=self._handle_ok)
        self.update_grid()

    def add_drives_toggle(self) -> None:
        if platform.system() == "Windows":
            drives = win32api.GetLogicalDriveStrings().split("\000")[:-1]
            self.drives_toggle = ui.toggle(drives, value=drives[0], on_change=self.update_drive)

    def update_drive(self) -> None:
        self.path = Path(self.drives_toggle.value).expanduser()
        self.update_grid()

    def update_grid(self) -> None:
        paths = list(self.path.glob("*"))
        if not self.show_hidden_files:
            paths = [p for p in paths if not p.name.startswith(".")]
        paths.sort(key=lambda p: p.name.lower())
        paths.sort(key=lambda p: not p.is_dir())

        self.grid.options["rowData"] = [
            {
                "name": f"📁 <strong>{p.name}</strong>" if p.is_dir() else p.name,
                "path": str(p.absolute()),
            }
            for p in paths
        ]
        if (self.upper_limit is None and self.path != self.path.parent) or (
            self.upper_limit is not None and self.path != self.upper_limit
        ):
            self.grid.options["rowData"].insert(
                0,
                {
                    "name": "📁 <strong>..</strong>",
                    "path": str(self.path.parent),
                },
            )
        self.grid.update()

    def handle_double_click(self, e: events.GenericEventArguments) -> None:
        path = Path(e.args["data"]["path"])
        if path.is_dir():
            self.path = path
            self.update_grid()

    async def _handle_ok(self) -> None:
        if row := await self.grid.get_selected_row():
            self.submit(row["path"])
