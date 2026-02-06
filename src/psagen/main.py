"""Application Entry Point."""

import os

from nicegui import ui

from psagen.core.settings import settings
from psagen.ui.app import configure_app
from psagen.ui.pages.home import home_page  # noqa: F401

if __name__ in {"__main__", "__mp_main__"}:
    configure_app()

    # Use a stable secret to persist sessions across server reloads
    storage_secret = os.environ.get(
        "NICEGUI_STORAGE_SECRET", "polarsteps_album_generator_dev_secret"
    )

    ui.run(
        title="Polarsteps Album Generator",
        favicon=settings.static_dir / "icon.svg",
        reload=True,
        storage_secret=storage_secret,
        show=False,
        dark=True,
        access_log=True,
    )
