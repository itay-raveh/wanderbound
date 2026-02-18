from __future__ import annotations

import asyncio
import shutil
import zipfile
from functools import partial
from io import BytesIO
from typing import TYPE_CHECKING, cast

from nicegui import app, ui
from nicegui.elements.upload_files import LargeFileUpload
from nicegui.storage import request_contextvar

from psagen.api.router import ALBUMS, api_router
from psagen.core.logger import get_logger
from psagen.core.settings import settings
from psagen.logic.album import Album
from psagen.models.config import AlbumConfig, AlbumSettings
from psagen.models.user import TripName, User
from psagen.ui.dialog import create_log_dialog
from psagen.ui.form import PydanticForm
from psagen.ui.preview import try_load_current_album_html

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from nicegui.events import UploadEventArguments

logger = get_logger(__name__)


def _trips_with_labels(trip_names: list[TripName]) -> dict[TripName, str]:
    return {name: name[: name.find("_")].title() for name in trip_names}


def _trip_select_for(user: User) -> ui.select:
    return (
        ui.select(_trips_with_labels(user.trip_names), value=user.selected_trip)
        .classes("w-full text-xl font-medium")
        .props("standout")
        .bind_value_to(user, "selected_trip")
        .bind_value_to(app.storage.user, "selected_trip")
    )


async def _handle_zip_upload(
    user: User, trip_select: ui.select, event: UploadEventArguments
) -> None:
    logger.info("Extracting %s: %d MB", event.file.name, event.file.size() / 1024 // 1024)

    # noinspection PyProtectedMember
    file = (
        event.file._path if isinstance(event.file, LargeFileUpload) else BytesIO(event.file._data)  # noqa: SLF001  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportAttributeAccessIssue]
    )

    remove_target = user.folder
    loading = ui.notification("Extracting trips...", type="ongoing", spinner=True)
    try:
        with zipfile.ZipFile(file, "r") as zf:
            await asyncio.to_thread(zf.extractall, user.folder)

        user.trip_names = [path.name for path in user.trips_folder.iterdir()]
        trip_select.set_options(_trips_with_labels(user.trip_names))  # pyright: ignore[reportUnknownMemberType]

        msg = f"Found {len(user.trip_names)} trip(s)"
        logger.info(msg)
        ui.notify(msg, type="positive")

        remove_target = user.folder / "user"
    except (zipfile.BadZipFile, FileNotFoundError):
        msg = f"'{event.file.name}' is a corrupted file or is not a Polarsteps export"
        ui.notify(msg, type="negative")
        cast("ui.upload", event.sender).reset()
    finally:
        loading.dismiss()
        if remove_target.exists():
            # noinspection PyTypeChecker
            await asyncio.to_thread(shutil.rmtree, remove_target)


_POLARSTEPS_EXPORT_INSTRUCTIONS = """
### Download a copy of your Polarsteps data:

- Log in at [Polarsteps](https://www.polarsteps.com) using a laptop or desktop computer.
- Click on your name on the top right of the page and select **Account settings**.
- Scroll down to **Download my data** in the privacy section.
- Click the blue link to **Download a copy of your data**.
- Click **Start My Archive**.
- You will receive an email with a link to download a file with your data.
"""


@ui.page("/register")
async def register_page() -> None:
    ui.on_exception(handle_exception)
    ui.add_css(settings.static_dir / "style.css")

    request = request_contextvar.get()
    if request is None:
        # Client is not connected, let's reload
        ui.navigate.reload()
        return

    # Create an illegal empty user so we can use the `.folder` method etc.
    user = User(id=cast("str", request.session["id"]), trip_names=[], selected_trip=None)  # pyright: ignore[reportArgumentType]

    if user.folder.exists():
        # noinspection PyTypeChecker
        await asyncio.to_thread(shutil.rmtree, user.folder)

    with ui.column().classes(
        "w-full h-screen items-center justify-center p-4 bg-gradient-to-br from-dark to-black"
    ):
        # Hero Section
        with ui.column().classes("items-center text-center mb-12"):
            with ui.row().classes("items-center"):
                ui.image("/static/icon.svg").classes("size-24")
                ui.label("Polarsteps Album Generator").classes(
                    "text-4xl font-bold tracking-tight mb-2 text-primary"
                )
            ui.label("Turn your adventures into beautiful, printable albums.").classes(
                "text-xl text-gray-400 font-medium"
            )

        with (
            ui.dialog().props('backdrop-filter="blur(6px)"') as d,
            ui.card().classes("p-8 max-w-2xl w-full flex items-center"),
        ):
            ui.markdown(_POLARSTEPS_EXPORT_INSTRUCTIONS, sanitize=False)

        with ui.card().classes("w-full max-w-2xl p-12 backdrop-blur-md items-center"):
            with ui.row().classes("items-center"):
                ui.markdown("Upload your **user_data.zip** to begin").classes(
                    "text-2xl text-center"
                )
                ui.button(icon="help_outline", color=None, on_click=d.open).props("flat dense")

            upload = ui.upload(auto_upload=True).props("accept=.zip flat").classes("w-full h-32")

            trip_select = (
                _trip_select_for(user)
                # Once we have trips, allow the user to select one
                .bind_enabled_from(user, "trip_names", bool)
                .on_value_change(user.store)
            )

            upload.on_upload(partial(_handle_zip_upload, user, trip_select))

            (
                # Once they do that, allow them to return to the home page
                ui.button("Let's go!", icon="auto_awesome", on_click=lambda: ui.navigate.to(home))
                .classes("size-full")
                .bind_enabled_from(user, "selected_trip", bool)
            )


CONFIGS: dict[TripName, AlbumConfig] = {}


def _make_generate_on_click(user: User, frame: ui.element) -> Callable[[], Awaitable[None]]:
    async def on_click() -> None:
        d, log = create_log_dialog("Generating Album...", "auto_awesome")

        with d:
            ALBUMS[user.selected_trip] = await Album.generate(
                user, CONFIGS[user.selected_trip], log.push
            )
        d.close()

        await try_load_current_album_html(user, frame)

    return on_click


def _trip_name_to_settings(
    user: User, settings_form: PydanticForm, trip_name: TripName
) -> AlbumSettings:
    if trip_name not in CONFIGS:
        CONFIGS[trip_name] = AlbumConfig.from_trip_folder(user.trips_folder / trip_name)

    settings_form.on_value_change(lambda: CONFIGS[trip_name].persist_for(user))
    return CONFIGS[trip_name].settings


@ui.page("/")
async def home() -> None:
    ui.on_exception(handle_exception)
    ui.add_css(settings.static_dir / "style.css")

    try:
        user = User.from_storage()
    except (TypeError, KeyError):
        ui.navigate.to(register_page)
        return

    logger.info("%s", user)

    with ui.row().classes("w-full h-screen p-4 pb-8"):
        # Left: Album Select & Settings
        with ui.card().classes("w-2/7 h-full justify-between"):
            trip_select = _trip_select_for(user)

            ui.separator()

            settings_form = PydanticForm()
            settings_form.column.classes("w-full gap-3")

            ui.separator()

            generate_btn = ui.button("Generate Album", icon="auto_awesome").classes(
                "w-full text-lg font-bold shadow-lg"
            )

        # Right: Layout Editor (Preview)
        with ui.card().classes("flex-grow h-full"):
            frame = ui.element("iframe").classes("size-full rounded-lg").style("zoom: 0.8")
            frame.visible = False

    # On trip select update settings form
    trip_select.bind_value_to(
        settings_form, "instance", forward=partial(_trip_name_to_settings, user, settings_form)
    )

    # Generate and load album on generate click
    generate_btn.on_click(_make_generate_on_click(user, frame))

    # Enable button only when form has no errors
    generate_btn.bind_enabled_from(
        settings_form,
        "errors",
        backward=lambda errors: len(errors) == 0,  # pyright: ignore[reportAny]
    )


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
