from __future__ import annotations

import asyncio
import zipfile
from io import BytesIO
from typing import TYPE_CHECKING, cast

from nicegui import app, ui
from nicegui.binding import bind
from nicegui.elements.upload_files import FileUpload, LargeFileUpload
from nicegui.storage import request_contextvar

from psagen.api.router import ALBUMS, api_router
from psagen.core.logger import get_logger
from psagen.core.settings import settings
from psagen.logic.album import Album
from psagen.models.config import AlbumConfig, AlbumSettings
from psagen.models.user import TripName, User, get_user, set_user
from psagen.ui.dialog import create_log_dialog
from psagen.ui.form import PydanticForm
from psagen.ui.preview import (
    create_layout_editor_panel,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from nicegui.events import UploadEventArguments

logger = get_logger(__name__)


async def extract_zip_upload(user: User, upload: FileUpload) -> list[str]:
    logger.info("Extracting %d MB zip upload", upload.size() / 1024 // 1024)

    # noinspection PyProtectedMember
    file = upload._path if isinstance(upload, LargeFileUpload) else BytesIO(upload._data)  # noqa: SLF001  # pyright: ignore[reportUnknownArgumentType, reportAttributeAccessIssue, reportUnknownMemberType]

    try:
        # Extract from disk
        with zipfile.ZipFile(file, "r") as zf:
            # Validate it's a Polarsteps export (should have trip.json files)
            file_list = zf.namelist()
            trip_jsons = [f for f in file_list if f.endswith("trip.json")]
            if not trip_jsons:
                msg = "Invalid Polarsteps export: no trip.json files found"
                raise ValueError(msg)

            def extract_to_trip_dir() -> None:
                for filename in file_list:
                    if filename.startswith("trip/"):
                        zf.extract(filename, user.folder)

            # Extract to trips directory
            await asyncio.to_thread(extract_to_trip_dir)

    except zipfile.BadZipFile as e:
        msg = f"Invalid zip file: {e}"
        raise ValueError(msg) from e

    trip_names = [path.name for path in user.trips_folder.iterdir()]
    logger.info("Extracted %d trips from upload: %s", len(trip_names), ", ".join(trip_names))

    return trip_names


async def handle_zip_upload(event: UploadEventArguments) -> None:
    loading = ui.notification("Extracting...", type="ongoing", spinner=True)

    request = request_contextvar.get()
    if request is None:
        # Something is wrong with the cookie, let's reload
        ui.navigate.reload()
        return

    user = User(id=request.session["id"], trip_names=[])  # pyright: ignore[reportAny]
    user.folder.mkdir(parents=True, exist_ok=True)

    try:
        user.trip_names = await extract_zip_upload(user, event.file)
    except ValueError as e:
        loading.dismiss()
        ui.notify(str(e), type="negative")
        cast("ui.upload", event.sender).reset()
    else:
        loading.dismiss()
        set_user(user)
        ui.notify(f"Found {len(user.trip_names)} trip(s)", type="positive")
        ui.navigate.to(home)


@ui.page("/register")
async def register_page() -> None:
    ui.on_exception(handle_exception)
    ui.add_css(settings.static_dir / "style.css")

    with ui.column().classes(
        "w-full h-screen items-center justify-center p-4 bg-gradient-to-br from-dark to-black"
    ):
        # Hero Section
        with ui.column().classes("items-center text-center mb-12"):
            ui.image("/static/icon.svg").classes("w-24 h-24 mb-4 opacity-90")
            ui.label("Polarsteps Album Generator").classes(
                "text-4xl font-bold tracking-tight mb-2 text-primary"
            )
            ui.label("Turn your adventures into beautiful, printable albums.").classes(
                "text-xl text-gray-400 font-medium"
            )

        # Main Card
        with ui.card().classes(
            "w-full max-w-2xl p-8 shadow-2xl border-none bg-opacity-50 backdrop-blur-md"
        ):
            ui.label("Get Started").classes("text-2xl font-semibold mb-6 text-center w-full")

            with ui.column().classes("gap-4 items-center w-full"):
                ui.markdown(
                    "Upload your **Polartsteps Data Export** ZIP file below to begin."
                ).classes("text-center mb-2")

                ui.upload(
                    on_upload=handle_zip_upload,
                    auto_upload=True,
                ).props("accept=.zip flat color=primary").classes("w-full h-32")


CONFIGS: dict[TripName, AlbumConfig] = {}


def _make_generate_on_click(
    user: User, load_current_album_html: Callable[[], Awaitable[None]]
) -> Callable[[], Awaitable[None]]:
    async def on_click() -> None:
        if user.selected_trip is None:
            raise RuntimeError("Impossible")

        d, log = create_log_dialog("Generating Album...", "auto_awesome")

        with d:
            ALBUMS[user.selected_trip] = await Album.generate(
                user, CONFIGS[user.selected_trip], log.push
            )
        d.close()

        await load_current_album_html()

    return on_click


def _make_form_forward(user: User) -> Callable[[TripName | None], AlbumSettings | None]:
    def forward(trip_name: TripName | None) -> AlbumSettings | None:
        if trip_name is None:
            return None
        if trip_name not in CONFIGS:
            CONFIGS[trip_name] = AlbumConfig.from_trip_folder(user.trips_folder / trip_name)
        return CONFIGS[trip_name].settings

    return forward


@ui.page("/")
async def home() -> None:
    ui.on_exception(handle_exception)

    try:
        user = get_user()
    except (TypeError, KeyError):
        ui.navigate.to(register_page)
        return

    ui.add_css(settings.static_dir / "style.css")

    # Bind the storage dict to the typed user object
    bind(user, "selected_trip", app.storage.user, "selected_trip")

    with ui.row().classes("w-full h-screen p-4 pb-8"):
        # Left: Album Select & Settings
        with (
            ui.card().classes("w-2/7 h-full"),
            ui.column().classes("size-full justify-between gap-0"),
        ):
            trip_select = (
                ui.select(
                    value=user.selected_trip,
                    options={name: name[: name.find("_")].title() for name in user.trip_names},
                )
                .classes("w-full text-xl font-medium")
                .props("outlined")
            )

            ui.separator().classes("mt-4 mb-4")

            settings_form = PydanticForm()
            settings_form.elem.classes("size-full")

            trip_select.bind_value_to(user, "selected_trip")
            trip_select.bind_value_to(settings_form, "instance", forward=_make_form_forward(user))

            generate_btn = ui.button("Generate Album", icon="auto_awesome").classes(
                "w-full text-lg font-bold shadow-lg"
            )
            generate_btn.bind_enabled_from(
                settings_form,
                "errors",
                backward=lambda errors: len(errors) == 0,  # pyright: ignore[reportAny]
            )

        # Right: Layout Editor (Preview)
        with ui.card().classes("flex-grow h-full"):
            load_current_album_html = await create_layout_editor_panel(user)

    # Load album on trip select
    trip_select.on_value_change(load_current_album_html)

    # Generate and load album on generate click
    generate_btn.on_click(_make_generate_on_click(user, load_current_album_html))


def handle_exception(e: Exception) -> None:
    logger.exception("Unexpected error", exc_info=e)

    # Use the shared dialog component with error styling
    _, log = create_log_dialog("An unexpected error occurred", "error", color="red-500")
    log.push(str(e))


if __name__ in {"__main__", "__mp_main__"}:
    app.colors(
        primary="#4a9eff",
        secondary="#ffd700",
        accent="#ff007f",
        dark="#1a1a2e",
        positive="#21ba45",
        negative="#c10015",
        info="#31ccec",
        warning="#f2c037",
    )

    # Mount Static Files
    app.add_static_files("/static", settings.static_dir)
    app.mount("/api", api_router)

    ui.run(  # pyright: ignore[reportUnknownMemberType]
        title="Polarsteps Album Generator",
        favicon=settings.static_dir / "icon.svg",
        dark=True,
        show=False,
        uvicorn_logging_level="info",
        uvicorn_reload_dirs=str(settings.project_root_dir),
        storage_secret=settings.storage_secret,
    )
