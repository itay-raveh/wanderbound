from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app import main
from app.core.config import get_settings

if TYPE_CHECKING:
    import pytest


async def test_frontend_serving_preserves_api_and_asset_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_frontend = getattr(main, "configure_frontend", None)
    assert configure_frontend is not None

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<h1>Wanderbound</h1>")
    (tmp_path / "assets" / "app.123.js").write_text("console.log('app')")

    application = FastAPI()

    @application.get("/api/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    app_settings = get_settings()
    monkeypatch.setattr(app_settings, "FRONTEND_DIRECTORY", tmp_path)
    configure_frontend(application, app_settings)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        api = await client.get("/api/ping", headers={"Accept": "text/html"})
        page = await client.get("/albums/one", headers={"Accept": "text/html"})
        asset = await client.get("/assets/app.123.js")
        missing = await client.get("/assets/missing.js")

    assert api.json() == {"ok": True}
    assert page.text == "<h1>Wanderbound</h1>"
    assert page.headers["cache-control"] == "no-cache"
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert missing.status_code == 404
