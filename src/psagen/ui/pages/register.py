from __future__ import annotations

import asyncio
import shutil
import zipfile
from functools import partial
from io import BytesIO
from typing import TYPE_CHECKING, cast

from nicegui import ui
from nicegui.elements.upload_files import LargeFileUpload
from nicegui.storage import request_contextvar

from psagen.core.logger import get_logger
from psagen.core.settings import settings
from psagen.models.user import User
from psagen.ui.pages.exception import handle_exception
from psagen.ui.trip_select import _trips_with_labels, trip_select_for

_ANIMATE_SHAKE = "animate-[shake_3s_ease-in-out_infinite]"

if TYPE_CHECKING:
    from nicegui.events import UploadEventArguments

logger = get_logger(__name__)


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

    if await user.folder.exists():
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
            ui.card().classes("p-8 max-w-3xl w-full flex items-center"),
        ):
            ui.markdown(_POLARSTEPS_EXPORT_INSTRUCTIONS, sanitize=False)

        with ui.card().classes("w-full max-w-2xl p-12 backdrop-blur-md items-center"):
            with ui.row().classes("items-center"):
                ui.markdown("Upload your **user_data.zip** to begin").classes(
                    "text-2xl text-center"
                )
                ui.button(icon="help_outline", color=None, on_click=d.open).props("flat dense")

            upload = (
                ui.upload(auto_upload=True)
                .props("accept=.zip")
                .classes("w-full")
                .classes(_ANIMATE_SHAKE)
            )

            trip_select = (
                trip_select_for(user)
                # Once we have trips, allow the user to select one
                .bind_enabled_from(user, "trip_names", bool)
                .on_value_change(user.store)
                .on_value_change(lambda: ui.navigate.to("/?new=true"))
            )

            upload.on_upload(partial(_handle_zip_upload, user, trip_select))


_POLARSTEPS_EXPORT_INSTRUCTIONS = """
### Download a copy of your Polarsteps data:

- Log in at [Polarsteps](https://www.polarsteps.com) using a laptop or desktop computer.
- Click on your name on the top right of the page and select **Account settings**.
- Scroll down to **Download my data** in the privacy section.
- Click the blue link to **Download a copy of your data**.
- Click **Start My Archive**.
- You will receive an email with a link to download a file with your data.
"""


async def _handle_zip_upload(
    user: User, trip_select: ui.select, event: UploadEventArguments
) -> None:
    logger.info("Extracting %s: %d MB", event.file.name, event.file.size() / 1024 // 1024)

    # noinspection PyProtectedMember
    file = (
        event.file._path if isinstance(event.file, LargeFileUpload) else BytesIO(event.file._data)  # noqa: SLF001  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportAttributeAccessIssue]
    )

    uploader = cast("ui.upload", event.sender)

    remove_target = user.folder
    loading = ui.notification("Extracting trips...", type="ongoing", spinner=True)
    try:
        with zipfile.ZipFile(file, "r") as zf:
            await asyncio.to_thread(zf.extractall, user.folder)

        user.trip_names = [path.name async for path in user.trips_folder.iterdir()]
        trip_select.set_options(_trips_with_labels(user.trip_names))  # pyright: ignore[reportUnknownMemberType]

        uploader.classes(remove=_ANIMATE_SHAKE)
        trip_select.classes(_ANIMATE_SHAKE)

        msg = f"Found {len(user.trip_names)} trip(s)"
        logger.info(msg)
        ui.notify(msg, type="positive")

        remove_target = user.folder / "user"
    except (zipfile.BadZipFile, FileNotFoundError):
        msg = f"'{event.file.name}' is a corrupted file or is not a Polarsteps export"
        ui.notify(msg, type="negative")
        uploader.reset()
    finally:
        loading.dismiss()
        if await remove_target.exists():
            # noinspection PyTypeChecker
            await asyncio.to_thread(shutil.rmtree, remove_target)
