from nicegui import ui


def create_log_dialog(title: str, icon: str, color: str = "primary") -> tuple[ui.dialog, ui.log]:
    with ui.dialog() as d, ui.card().classes(f"w-full max-w-lg no-shadow border-{color} border-2"):
        with ui.row().classes(f"items-center gap-2 text-{color}"):
            ui.icon(icon, size="md")
            ui.label(title).classes("text-lg font-bold")

        ui.separator().classes(f"my-2 bg-{color} opacity-20")
        log = ui.log().classes("w-full h-48 bg-black/20 font-mono text-sm p-2 rounded")

        with ui.row().classes("w-full justify-end mt-2"):
            ui.button("Close", on_click=d.close).props(f"flat color={color}")

        d.open()
        return d, log
