"""Preview component with Album/Terminal switch."""

from nicegui import ui

from psagen.api.router import ALBUMS
from psagen.core.logger import get_logger
from psagen.models.user import User

logger = get_logger(__name__)


async def try_load_current_album_html(user: User, frame: ui.element) -> None:
    if (
        # we loaded the album for the trip (should be true)
        (album := ALBUMS.get(user.selected_trip))
        # and the album has been generated before
        and album.html_file.exists()
    ):
        path = album.html_file.relative_to(user.folder)
        t = album.html_file.stat().st_mtime
        await ui.run_javascript(f"getHtmlElement({frame.id}).src = '{path}?t={t}';")
        frame.visible = True
    else:
        frame.visible = False
