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
    ui.upload(
        label="Upload your Polarsteps `user_data.zip` file",
        on_upload=handle_zip_upload,
        auto_upload=True,
    ).props("accept=.zip flat").classes("w-full rounded-lg")


CONFIGS: dict[TripName, AlbumConfig] = {}


def _make_generate_on_click(
    user: User, load_current_album_html: Callable[[], Awaitable[None]]
) -> Callable[[], Awaitable[None]]:
    async def on_click() -> None:
        if user.selected_trip is None:
            raise RuntimeError("Impossible")

        async for update in Album.generate(user, CONFIGS[user.selected_trip]):
            if isinstance(update, Album):
                update.save()
                ALBUMS[user.selected_trip] = update
                break

            ui.notify(update)

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
    except TypeError:
        ui.navigate.to(register_page)
        return

    ui.add_css(settings.static_dir / "style.css")

    # Bind the storage dict to the typed user object
    bind(user, "selected_trip", app.storage.user, "selected_trip")

    with ui.row().classes("w-full h-screen p-4 pb-8 gap-4 "):
        # Left: Album Select & Settings
        with ui.card().classes("w-1/5 h-full p-4 scroll-y"):
            trip_select = ui.select(
                value=user.selected_trip,
                options=user.trip_names,
                label="Select Trip",
            ).classes("w-full mt-4")

            generate_btn = ui.button("Generate", icon="play")
            settings_form = PydanticForm()

            trip_select.bind_value_to(user, "selected_trip")
            trip_select.bind_value_to(settings_form, "instance", forward=_make_form_forward(user))
            generate_btn.bind_enabled_from(settings_form, "ready", backward=bool)

        # Right: Layout Editor
        with ui.card().classes("flex-grow h-full p-4 flex flex-col"):
            load_current_album_html = await create_layout_editor_panel(user)

    # Load album on trip select
    trip_select.on_value_change(load_current_album_html)

    # Generate and load album on generate click
    generate_btn.on_click(_make_generate_on_click(user, load_current_album_html))


def handle_exception(e: Exception) -> None:
    logger.exception("Unexpected error", exc_info=e)

    with ui.dialog() as d, ui.card().classes("border-red-500 border-2"):
        with ui.row().classes("items-center gap-2 text-red-400"):
            ui.icon("error", size="md")
            ui.label("An unexpected error occurred").classes("text-lg font-bold")

        ui.separator().classes("my-2 bg-red-500 opacity-20")
        ui.log().classes("my-2 font-mono text-sm bg-black/20 p-2 rounded").push(str(e))

        with ui.row().classes("w-full justify-between items-center mt-2"):
            ui.button("Close", on_click=d.close).props("flat color=white")

    d.open()


if __name__ in {"__main__", "__mp_main__"}:
    app.colors(dar_page="#0f0f1a", accent="#4a9eff", positive="#10b981", warning="#f59e0b")

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
