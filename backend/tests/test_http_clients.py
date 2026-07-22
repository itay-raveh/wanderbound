from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from app.core.http_clients import lifespan_clients

if TYPE_CHECKING:
    import pytest


async def test_mapbox_clients_send_public_url_as_referrer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        PUBLIC_URL="https://wanderbound.example/",
        GOOGLE_CLIENT_ID="",
        GOOGLE_CLIENT_SECRET="",
    )
    monkeypatch.setattr("app.core.http_clients.get_settings", lambda: settings)

    async with lifespan_clients() as clients:
        assert clients.mapbox_matching.headers["Referer"] == settings.PUBLIC_URL
        assert clients.mapbox_directions.headers["Referer"] == settings.PUBLIC_URL
