from __future__ import annotations

from functools import partial
from typing import cast

from nicegui import ui
from nicegui.events import ValueChangeEventArguments

from psagen.api.router import ALBUMS
from psagen.core.logger import get_logger
from psagen.core.settings import settings
from psagen.logic.album import Album
from psagen.models.config import AlbumConfig
from psagen.models.user import TripName, User
from psagen.ui.dialog import create_log_dialog
from psagen.ui.form import PydanticForm
from psagen.ui.pages.exception import handle_exception
from psagen.ui.pages.register import register_page
from psagen.ui.trip_select import trip_select_for

logger = get_logger(__name__)


@ui.page("/")
async def home_page() -> None:
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
            trip_select = trip_select_for(user)

            ui.separator()

            settings_form = PydanticForm()
            settings_form.column.classes("w-full gap-3")

            ui.separator()

            generate_btn = ui.button("Generate Album", icon="auto_awesome").classes(
                "w-full text-lg font-bold shadow-lg"
            )

        # Right: Layout Editor (Preview)
        with ui.card().classes("flex-grow h-full"):
            preview_frame = ui.element("iframe").classes("size-full rounded-lg").style("zoom: 0.8")
            preview_frame.visible = False

    # On trip select update settings form and hide preview
    trip_select.on_value_change(partial(_set_settings_instance, user, settings_form))
    trip_select.on_value_change(lambda _: preview_frame.set_visibility(False))

    # Trigger this manually once
    # noinspection PyTypeChecker
    await _set_settings_instance(
        user,
        settings_form,
        ValueChangeEventArguments(sender=None, client=None, value=user.selected_trip),  # pyright: ignore[reportArgumentType]
    )

    # Generate and load album on generate click
    generate_btn.on_click(partial(_generate_on_click, user, preview_frame))

    # Enable button only when form has no errors
    generate_btn.bind_enabled_from(
        settings_form,
        "ready",
    )


CONFIGS: dict[TripName, AlbumConfig] = {}


async def _set_settings_instance(
    user: User, settings_form: PydanticForm, ev: ValueChangeEventArguments
) -> None:
    trip_name = cast("TripName | None", ev.value)

    if trip_name is None:
        return

    if trip_name not in CONFIGS:
        CONFIGS[trip_name] = await AlbumConfig.from_trip_folder(user.trips_folder / trip_name)

    settings_form.on_value_change(partial(CONFIGS[trip_name].persist_for, user))
    settings_form.instance = CONFIGS[trip_name].settings


async def _generate_on_click(user: User, frame: ui.element) -> None:
    d, log = create_log_dialog("Generating Album...", "auto_awesome")

    with d:
        ALBUMS[user.selected_trip] = await Album.generate(
            user, CONFIGS[user.selected_trip], log.push
        )
    d.close()

    path = ALBUMS[user.selected_trip].html_file.relative_to(user.folder)
    stat = await ALBUMS[user.selected_trip].html_file.stat()
    await frame.run_method("setAttribute", "src", f"{path}?t={stat.st_mtime_ns}")
    frame.visible = True
