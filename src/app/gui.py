"""GUI entry point for the album generator using NiceGUI."""

# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportAny=false, reportExplicitAny=false

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from time import time
from typing import IO, TYPE_CHECKING, Any

import httpx
from nicegui import app, ui
from pydantic import ValidationError

from src.app.api import api_router
from src.app.engine import get_album_service, get_generator_args, try_get_generator_args
from src.core.cache import clear_cache
from src.core.logger import TeeIO, get_logger, set_console
from src.core.session import get_session_id

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)

# ============================================================================
# DESIGN SYSTEM
# ============================================================================

# Color Palette (Polarsteps-inspired warm travel tones)
COLORS = {
    "bg_dark": "#0f0f1a",  # Deep navy background
    "bg_card": "#1a1a2e",  # Card background
    "bg_input": "#252540",  # Input background
    "accent": "#4a9eff",  # Primary blue accent
    "accent_hover": "#6bb3ff",  # Hover state
    "success": "#10b981",  # Green for success states
    "warning": "#f59e0b",  # Amber for warnings
    "text": "#e5e7eb",  # Primary text
    "text_muted": "#9ca3af",  # Secondary text
    "border": "#374151",  # Borders
}

# Typography
FONTS = "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif"

# Spacing scale (in pixels)
SPACING = {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32}

# CSS Design System
DESIGN_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
@import url('https://fonts.googleapis.com/icon?family=Material+Icons');

:root {{
    --bg-dark: {COLORS["bg_dark"]};
    --bg-card: {COLORS["bg_card"]};
    --bg-input: {COLORS["bg_input"]};
    --accent: {COLORS["accent"]};
    --accent-hover: {COLORS["accent_hover"]};
    --success: {COLORS["success"]};
    --text: {COLORS["text"]};
    --text-muted: {COLORS["text_muted"]};
    --border: {COLORS["border"]};
}}

* {{ font-family: {FONTS}; }}

body {{ 
    background: var(--bg-dark) !important; 
    color: var(--text);
    overflow: hidden;
}}

/* Cards */
.q-card {{ 
    background: var(--bg-card) !important; 
    border: 1px solid var(--border);
    border-radius: 12px !important;
}}

/* Inputs */
.q-field--outlined .q-field__control {{
    border-color: var(--border) !important;
    background: var(--bg-input) !important;
    border-radius: 8px !important;
}}
.q-field--outlined .q-field__control:hover {{
    border-color: var(--accent) !important;
}}
.q-field__label {{ color: var(--text-muted) !important; }}

/* Buttons */
.q-btn--standard {{ border-radius: 8px !important; }}
.btn-primary {{
    background: linear-gradient(135deg, var(--accent), #3b82f6) !important;
    font-weight: 600 !important;
    letter-spacing: 0.5px;
}}
.btn-primary:hover {{ 
    background: linear-gradient(135deg, var(--accent-hover), #60a5fa) !important; 
}}

/* Expansions */
.q-expansion-item {{
    border: 1px solid var(--border);
    border-radius: 8px !important;
    margin-bottom: 8px;
    background: var(--bg-input) !important;
}}
.q-expansion-item__container {{ background: transparent !important; }}
.q-item__label {{ font-weight: 500; }}

/* Upload zone */
.q-uploader {{
    background: var(--bg-input) !important;
    border: 2px dashed var(--border) !important;
    border-radius: 12px !important;
}}
.q-uploader:hover {{ border-color: var(--accent) !important; }}

/* Remove all scrollbars by default */
.no-scroll {{ overflow: hidden !important; }}
.scroll-y {{ 
    overflow-y: auto !important; 
    overflow-x: hidden !important;
    scrollbar-width: thin;
    scrollbar-color: transparent transparent;
}}
.scroll-y:hover {{
    scrollbar-color: var(--border) transparent;
}}
.scroll-y::-webkit-scrollbar {{ width: 4px; }}
.scroll-y::-webkit-scrollbar-track {{ background: transparent; }}
.scroll-y::-webkit-scrollbar-thumb {{ 
    background: transparent; 
    border-radius: 2px; 
}}
.scroll-y:hover::-webkit-scrollbar-thumb {{
    background: var(--border);
}}

/* Terminal */
.xterm .xterm-viewport {{
    scrollbar-width: thin !important;
}}
.xterm .xterm-viewport::-webkit-scrollbar {{
    width: 6px !important;
}}

/* Custom Button Styling */
.custom-btn {{
    border-radius: 8px !important;
    font-weight: 600 !important;
    text-transform: none !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06) !important;
    transition: all 0.2s ease !important;
}}
.custom-btn:hover {{
    transform: translateY(-1px);
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05) !important;
}}
.btn-generate {{
    background: linear-gradient(135deg, var(--accent), #2563eb) !important;
}}

/* Custom Upload Styling */
.custom-upload .q-uploader__header {{
    background: transparent !important;
    color: var(--text-muted) !important;
}}
.custom-upload .q-uploader__list {{
    background: transparent !important;
    padding: 0 !important;
}}
.custom-upload {{
    background: var(--bg-input) !important;
    border: 1px dashed var(--border) !important;
    box-shadow: none !important;
}}
.custom-upload:hover {{
    border-color: var(--accent) !important;
    background: rgba(74, 158, 255, 0.05) !important;
}}

/* Remove padding from main page container specifically (NiceGUI default) */
.nicegui-content {{
    padding: 0 !important;
    margin: 0 !important;
}}
"""

# Terminal styling
TERMINAL_THEME = {
    "foreground": COLORS["text"],
    "background": COLORS["bg_card"],
    "selection": "#97979b33",
    "cursor": COLORS["accent"],
}


# noinspection PyAbstractClass
class FileCompatXTerm(ui.xterm, IO[str]):  # pyright: ignore[reportIncompatibleMethodOverride]
    def flush(self) -> None:
        self.update()


def create_setup_panel(on_generate: Callable[[], Any]) -> None:
    """Create the streamlined setup panel."""
    from src.core.session import extract_zip_upload, get_output_dir, get_trips_dir  # noqa: PLC0415

    trips_key = "_available_trips"
    selected_trip_key = "_selected_trip"
    trip_select: ui.select | None = None

    async def handle_upload(event: Any) -> None:
        nonlocal trip_select
        loading = ui.notification("Extracting...", type="ongoing", spinner=True)
        try:
            trips = await extract_zip_upload(event)
            app.storage.user[trips_key] = trips
            if trip_select:
                trip_select.options = trips
                # trip_select.set_visibility(True) # Always visible now
                if trips:
                    trip_select.enable()
                    app.storage.user[selected_trip_key] = trips[0]
                    trip_select.value = trips[0]
                    _update_paths(trips[0])
                else:
                    trip_select.disable()
            loading.dismiss()
            ui.notify(f"Found {len(trips)} trip(s)", type="positive")
        except ValueError as e:
            loading.dismiss()
            ui.notify(str(e), type="negative")

    def _update_paths(trip_slug: str) -> None:
        if not trip_slug:
            return
        app.storage.user["trip"] = str(get_trips_dir() / trip_slug)
        app.storage.user["output"] = str(get_output_dir())

    def on_trip_change(e: Any) -> None:
        app.storage.user[selected_trip_key] = e.value
        if e.value:
            _update_paths(e.value)
        validate_form()  # Force validation update

    async def handle_cover_upload(event: Any, field: str) -> None:
        """Handle cover image upload."""
        # Simple validation: check extension
        if not event.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            ui.notify("Only image files are allowed", type="warning")
            return

        try:
            output_dir = Path(app.storage.user.get("output", "/tmp"))
            output_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{field}_{event.name}"
            filepath = output_dir / filename
            filepath.write_bytes(event.content.read())
            app.storage.user[field] = str(filepath)
            ui.notify(f"{field.replace('_', ' ').title()} set", type="positive")
        except Exception as e:
            ui.notify(f"Failed to save image: {e}", type="negative")

    # --- Header with logo ---
    with ui.row().classes("w-full items-center gap-3 mb-6 pl-1"):
        ui.image("/static/icon.svg").classes("w-8 h-8 drop-shadow-md")
        ui.label("Album Generator").classes("text-xl font-bold tracking-tight")

    # --- Upload Section ---
    ui.upload(
        label="Drop .zip file here",
        on_upload=handle_upload,
        auto_upload=True,
    ).props("accept=.zip flat color=primary").classes("w-full custom-upload rounded-lg")

    trip_select = (
        ui.select(options=[], label="Select Trip", on_change=on_trip_change)
        .classes("w-full mt-4")
        .bind_value(app.storage.user, selected_trip_key)
    )
    # Ensure options persist from storage
    stored_trips = app.storage.user.get(trips_key, [])
    if stored_trips:
        trip_select.options = stored_trips
        trip_select.enable()
    else:
        trip_select.disable()

    # Validation visual for trip selector
    ui.timer(
        1.0,
        lambda: trip_select.props(
            "error" if (not trip_select.value and not trip_select.disable) else ""
        ),
    )

    async def test_weather_key() -> None:
        """Test the Visual Crossing API key."""
        key = app.storage.user.get("weather_api_key")
        if not key:
            ui.notify("Please enter an API key first", type="warning")
            return

        with ui.dialog() as dialog, ui.card():
            ui.label("Testing API Key...")
            spinner = ui.spinner("dots")

        dialog.open()

        try:
            async with httpx.AsyncClient() as client:
                # Lightweight call to check key validity
                resp = await client.get(
                    "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/London",
                    params={"key": key, "include": "current"},
                    timeout=10.0,
                )
                dialog.close()

                if resp.status_code == 200:
                    ui.notify("API Key is valid!", type="positive")
                elif resp.status_code == 401:
                    ui.notify("Invalid API Key (401 Unauthorized)", type="negative")
                else:
                    ui.notify(f"API Error: {resp.status_code}", type="negative")
        except Exception as e:
            dialog.close()
            ui.notify(f"Connection Failed: {e!s}", type="negative")

    # State for validation UI updates
    customize_expansion: ui.expansion | None = None
    advanced_expansion: ui.expansion | None = None
    generate_btn: ui.button | None = None

    def validate_form() -> bool:
        """Check validation and update UI indicators."""
        is_trip_selected = bool(app.storage.user.get(selected_trip_key))
        args_valid = False
        error_fields: set[str] = set()

        try:
            get_generator_args()
            args_valid = True
        except ValidationError as e:
            for err in e.errors():
                loc = err["loc"]
                if loc:
                    error_fields.add(str(loc[0]))
        except ValueError:
            # Handle slice errors usually coming from args.py logic not captured by Pydantic directly if any
            # But args.py validators raise ValueError which Pydantic catches and wraps ?
            # Actually args.py raises ValueError in validators, which wraps into ValidationError usually.
            pass

        # Update Customize Section Style
        customize_errors = {"title", "subtitle", "steps", "maps", "cover", "back_cover"}
        if customize_expansion:
            if any(f in error_fields for f in customize_errors):
                customize_expansion.props("header-class=text-red-400 icon=error_outline")
            else:
                customize_expansion.props("header-class='' icon=tune")

        # Update Advanced Section Style
        advanced_errors = {"weather_api_key", "no_cache"}
        if advanced_expansion:
            if any(f in error_fields for f in advanced_errors):
                advanced_expansion.props("header-class=text-red-400 icon=error_outline")
            else:
                advanced_expansion.props("header-class='' icon=settings")

        # Update Generate Button
        can_generate = is_trip_selected and args_valid
        if generate_btn:
            if can_generate:
                generate_btn.enable()
            else:
                generate_btn.disable()

            # Update look for no-cache logic
            if app.storage.user.get("no_cache"):
                generate_btn.props("color=warning icon=refresh")
                generate_btn.text = "UPDATE CACHE & GENERATE"
            else:
                generate_btn.props("color='' icon=play_arrow")
                generate_btn.classes(remove="bg-warning")
                generate_btn.text = "GENERATE ALBUM"

        return can_generate

    # Auto-validate when storage changes
    # We can't easily hook into storage changes generally, so we'll poll or hook inputs.
    # Hooking on_change of every input is verbose.
    # A simple timer is effective for this "reactive" local state.
    ui.timer(1.0, validate_form)

    # --- Generate Button ---
    generate_btn = ui.button("GENERATE ALBUM", icon="play_arrow", on_click=on_generate).classes(
        "w-full mt-6 py-3 text-base custom-btn btn-generate"
    )
    # Note: We manage enable/disable manually in validate_form now, removing bind_enabled_from to avoid conflict

    ui.separator().classes("my-6 opacity-20")

    # --- Customize Section ---
    with ui.expansion("Customize Album", icon="tune", value=False).classes(
        "w-full rounded-lg overflow-hidden"
    ) as customize_expansion:
        ui.input("Title", placeholder="Override trip title").classes("w-full").bind_value(
            app.storage.user, "title"
        )
        ui.input("Subtitle", placeholder="Override subtitle").classes("w-full mt-2").bind_value(
            app.storage.user, "subtitle"
        )

        ui.label("Cover Photo").classes(
            "text-xs font-semibold text-gray-500 uppercase tracking-wider mt-4 mb-2"
        )
        ui.upload(
            label="Upload front cover image",
            on_upload=lambda e: handle_cover_upload(e, "cover"),
            auto_upload=True,
        ).props("accept=image/* flat hint='Only .jpg, .png, .webp'").classes(
            "w-full custom-upload rounded-lg h-16"
        )
        ui.label("Customize the main album cover").classes("text-xs text-gray-500 mt-1 italic")

        ui.label("Back Cover").classes(
            "text-xs font-semibold text-gray-500 uppercase tracking-wider mt-4 mb-2"
        )
        ui.upload(
            label="Upload back cover image",
            on_upload=lambda e: handle_cover_upload(e, "back_cover"),
            auto_upload=True,
        ).props("accept=image/* flat hint='Only .jpg, .png, .webp'").classes(
            "w-full custom-upload rounded-lg h-16"
        )
        ui.label("Optional image for the back of the album").classes(
            "text-xs text-gray-500 mt-1 italic"
        )

        ui.input(
            "Steps to Include",
            placeholder="e.g. 1-5, 8, 10-12",
        ).classes("w-full mt-4").props('hint="Leave empty to include all steps"').bind_value(
            app.storage.user, "steps"
        )

        ui.input(
            "Map Step Ranges",
            placeholder="e.g. 1-3, 5",
        ).classes("w-full mt-2").props(
            'hint="Ranges of steps that will have a map generated"'
        ).bind_value(app.storage.user, "maps")

    # --- Advanced Section ---
    with ui.expansion("Advanced", icon="settings", value=False).classes(
        "w-full rounded-lg overflow-hidden mt-2"
    ) as advanced_expansion:
        ui.checkbox("Force cache update").bind_value(app.storage.user, "no_cache").props(
            'color="warning"'
        )
        ui.label("Re-fetch data even if cached (slower)").classes(
            "text-xs text-gray-500 ml-8 -mt-2 mb-2"
        )

        with ui.row().classes("w-full items-start gap-2"):
            ui.input(
                "Weather API Key",
                placeholder="Visual Crossing API key",
                password=True,
                password_toggle_button=True,
            ).classes("flex-grow").props('hint="Required for historical weather data"').bind_value(
                app.storage.user, "weather_api_key"
            )

            ui.button(icon="check", on_click=test_weather_key).props("flat round dense").classes(
                "mt-4 text-gray-400 hover:text-green-500"
            ).tooltip("Test API Key")

        ui.link(
            "Get a free API key →",
            "https://www.visualcrossing.com/sign-up",
            new_tab=True,
        ).classes("text-xs text-accent mt-1 hover:underline")


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
        import json  # noqa: PLC0415

        from src.models.layout import AlbumLayout  # noqa: PLC0415

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
    from rich.console import Console  # noqa: PLC0415

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
    tee = TeeIO(sys.stdout, terminal)
    console = Console(file=tee, width=width or 120, height=height or 40, force_terminal=True)
    set_console(console)

    layout_toolbar = create_layout_toolbar()
    return album_frame, terminal, layout_toolbar


async def show_album_frame(album_frame: ui.element, layout_toolbar: ui.row) -> None:
    """Display the generated album."""
    from src.core.session import get_session_id  # noqa: PLC0415

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
            logger.warning("Cleared cache")

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


@ui.page("/")
async def index_page() -> None:
    # Set Theme Colors
    ui.colors(
        primary=COLORS["accent"],
        secondary=COLORS["accent_hover"],
        accent=COLORS["success"],
        dark=COLORS["bg_dark"],
        positive=COLORS["success"],
        negative="#ef4444",
        warning=COLORS["warning"],
    )

    # Global Exception Handler
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

    ui.on_exception(handle_exception)

    # Inject design system CSS
    ui.add_head_html(f"<style>{DESIGN_CSS}</style>")

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


# Background cleanup
_background_tasks: set[asyncio.Task[None]] = set()


@app.on_startup
async def _start_background_tasks() -> None:
    from src.core.session import start_cleanup_task  # noqa: PLC0415

    task = asyncio.create_task(start_cleanup_task())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# Static files and API
STATIC_DIR = Path(__file__).parent.parent.parent / "static"
app.add_static_files("/static", STATIC_DIR)
app.mount("/api", api_router)

if __name__ in {"__main__", "__mp_main__"}:
    import os
    import secrets

    storage_secret = os.environ.get("NICEGUI_STORAGE_SECRET", secrets.token_hex(32))
    ui.run(
        title="Polarsteps Album Generator",
        favicon=STATIC_DIR / "icon.svg",
        dark=True,
        reload=True,
        uvicorn_reload_dirs="src,static",
        storage_secret=storage_secret,
    )
