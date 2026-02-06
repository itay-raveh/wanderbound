"""Sidebar component for setup and configuration."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from nicegui import app, ui
from nicegui.events import UploadEventArguments
from pydantic import ValidationError

from psagen.core.session import extract_zip_upload, get_output_dir, get_trips_dir
from psagen.logic.generator import get_generator_args


def create_setup_panel(on_generate: Callable[[], Any]) -> None:
    """Create the streamlined setup panel."""
    trips_key = "_available_trips"
    selected_trip_key = "_selected_trip"
    trip_select: ui.select | None = None

    # State validation elements
    customize_expansion: ui.expansion | None = None
    advanced_expansion: ui.expansion | None = None
    generate_btn: ui.button | None = None

    async def handle_upload(event: UploadEventArguments) -> None:
        nonlocal trip_select
        loading = ui.notification("Extracting...", type="ongoing", spinner=True)
        try:
            trips = await extract_zip_upload(event)
            app.storage.user[trips_key] = trips
            if trip_select:
                trip_select.options = trips
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
            event.sender.reset()
            ui.notify(str(e), type="negative")

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

    ui.timer(1.0, validate_form)

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
    ).props("accept=.zip flat").classes("w-full custom-upload rounded-lg")

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
            ui.spinner("dots")

        dialog.open()

        try:
            async with httpx.AsyncClient() as client:
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

    # --- Generate Button ---
    generate_btn = ui.button("GENERATE ALBUM", icon="play_arrow", on_click=on_generate).classes(
        "w-full mt-6 py-3 text-base custom-btn btn-generate"
    )

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
            ).classes("flex-grow").props(
                'hint="If you want more accurate weather data, get a free API key from Visual Crossing"'
            ).bind_value(app.storage.user, "weather_api_key")

            ui.button(icon="check", on_click=test_weather_key).props("flat round dense").classes(
                "mt-4 text-gray-400 hover:text-green-500"
            ).tooltip("Test API Key")

        ui.link(
            "Get a free API key →",
            "https://www.visualcrossing.com/sign-up",
            new_tab=True,
        ).classes("text-xs text-accent mt-1 hover:underline")
