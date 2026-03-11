"""Typed Playwright browser singleton.

Populated during app lifespan, consumed via ``BrowserDep`` in endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Browser

_browser: Browser | None = None


def get_browser() -> Browser:
    if _browser is None:
        raise RuntimeError("Playwright browser not initialized")
    return _browser


def set_browser(browser: Browser) -> None:
    global _browser  # noqa: PLW0603
    _browser = browser


def clear_browser() -> None:
    global _browser  # noqa: PLW0603
    _browser = None
