from __future__ import annotations

from nicegui import app, ui

from psagen.api.router import api_router
from psagen.core.settings import settings
from psagen.ui.pages.home import home_page  # noqa: F401  # pyright: ignore[reportUnusedImport]
from psagen.ui.pages.register import (
    register_page,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)

if __name__ in {"__main__", "__mp_main__"}:
    app.colors(
        primary="#80bbff",
        secondary="#0053b3",
        accent="#ff007f",
        dark="#1a1a2e",
        positive="#21ba45",
        negative="#fc1c36",
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
