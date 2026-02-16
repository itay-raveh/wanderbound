"""Preview component with Album/Terminal switch."""

from collections.abc import Awaitable, Callable

from nicegui import ui

from psagen.api.router import ALBUMS
from psagen.core.logger import get_logger
from psagen.models.user import User

logger = get_logger(__name__)


async def create_layout_editor_panel(user: User) -> Callable[[], Awaitable[None]]:
    """Create the preview panel with album iframe & terminal."""
    # Create a frame to host the album
    frame = ui.element("iframe").classes("w-full flex-grow rounded-lg").style("zoom: 0.8")

    frame.visible = False

    # Create a callback to update the frame
    async def load_current_album_html() -> None:
        if (
            # A trip is selected (should be true)
            user.selected_trip is not None
            # and we loaded the album for that trip (should be true)
            and (album := ALBUMS.get(user.selected_trip))
            # and the album has been generated before
            and album.html_file.exists()
        ):
            path = album.html_file.relative_to(user.folder)
            t = album.html_file.stat().st_mtime
            await ui.run_javascript(
                # frame.src <- /.../album.html ? t={last edit time} (for cacheing)
                f"getHtmlElement({frame.id}).src = '{path}?t={t}';"
            )
            frame.visible = True
        else:
            frame.visible = False

    return load_current_album_html
