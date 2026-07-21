from pathlib import Path
from typing import TYPE_CHECKING

import anyio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app import frontend, main
from app.core.config import get_settings

if TYPE_CHECKING:
    import pytest


def test_main_does_not_own_frontend_delivery() -> None:
    assert not hasattr(main, "configure_frontend")
    assert not hasattr(main, "public_config")


async def test_frontend_serving_preserves_api_and_asset_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<h1>Wanderbound</h1>")
    (tmp_path / "assets" / "app.123.js").write_text("console.log('app')")

    application = FastAPI()

    @application.get("/api/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    app_settings = get_settings()
    monkeypatch.setattr(app_settings, "FRONTEND_DIRECTORY", tmp_path)
    frontend.install_frontend(application, app_settings)

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


async def test_frontend_csp_allows_virtual_hosted_uploads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "index.html").write_text("<h1>Wanderbound</h1>")
    application = FastAPI()
    app_settings = get_settings()
    monkeypatch.setattr(app_settings, "FRONTEND_DIRECTORY", tmp_path)
    monkeypatch.setattr(
        app_settings,
        "UPLOAD_S3_PUBLIC_ENDPOINT_URL",
        "https://fsn1.your-objectstorage.com",
    )
    monkeypatch.setattr(app_settings, "UPLOAD_S3_BUCKET", "wanderbound-uploads")
    monkeypatch.setattr(app_settings, "UPLOAD_S3_ADDRESSING_STYLE", "virtual")
    frontend.install_frontend(application, app_settings)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/", headers={"Accept": "text/html"})

    policy = response.headers["content-security-policy"]
    assert "https://wanderbound-uploads.fsn1.your-objectstorage.com" in policy


async def test_frontend_renders_absolute_social_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_index = anyio.Path(__file__).parent.parent.parent / "frontend" / "index.html"
    await (anyio.Path(tmp_path) / "index.html").write_text(
        await source_index.read_text()
    )
    application = FastAPI()
    app_settings = get_settings()
    monkeypatch.setattr(app_settings, "FRONTEND_DIRECTORY", tmp_path)
    monkeypatch.setattr(app_settings, "PUBLIC_URL", "https://example.test")
    frontend.install_frontend(application, app_settings)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/albums/one", headers={"Accept": "text/html"})

    assert '<meta property="og:url" content="https://example.test/" />' in response.text
    assert (
        '<meta property="og:image" content="https://example.test/og-image.png" />'
        in response.text
    )
    assert (
        '<meta name="twitter:image" content="https://example.test/og-image.png" />'
        in response.text
    )
    assert '<link rel="canonical" href="https://example.test/" />' in response.text


async def test_frontend_does_not_rewrite_partial_html_responses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = b"__WANDERBOUND_PUBLIC_URL__"
    body = b"<html>" + marker + b"</html>"
    (tmp_path / "index.html").write_bytes(body)
    application = FastAPI()
    app_settings = get_settings()
    monkeypatch.setattr(app_settings, "FRONTEND_DIRECTORY", tmp_path)
    monkeypatch.setattr(app_settings, "PUBLIC_URL", "https://example.test")
    frontend.install_frontend(application, app_settings)
    start = body.index(marker)
    end = start + len(marker) - 1

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get(
            "/index.html", headers={"Range": f"bytes={start}-{end}"}
        )

    assert response.status_code == 206
    assert response.content == marker
    assert response.headers["content-range"] == f"bytes {start}-{end}/{len(body)}"


async def test_frontend_does_not_report_the_unrendered_length_for_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "index.html").write_text("<html>__WANDERBOUND_PUBLIC_URL__</html>")
    application = FastAPI()
    app_settings = get_settings()
    monkeypatch.setattr(app_settings, "FRONTEND_DIRECTORY", tmp_path)
    frontend.install_frontend(application, app_settings)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.head("/index.html")

    assert response.status_code == 200
    assert "content-length" not in response.headers
