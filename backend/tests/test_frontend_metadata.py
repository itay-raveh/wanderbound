from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import AnyHttpUrl

from app.core.config import get_settings
from app.frontend import install_frontend

FRONTEND_DIRECTORY = Path(__file__).resolve().parents[2] / "frontend"


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: dict[str, str] = {}
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        rel = attributes.get("rel")
        if tag == "link" and rel:
            self.links[rel] = attributes.get("href") or ""
        if tag == "meta":
            key = attributes.get("property") or attributes.get("name")
            if key:
                self.meta[key] = attributes.get("content") or ""


@pytest.mark.anyio
async def test_social_metadata_uses_runtime_public_url() -> None:
    settings = get_settings().model_copy(
        update={
            "FRONTEND_DIRECTORY": FRONTEND_DIRECTORY,
            "PUBLIC_URL": AnyHttpUrl("https://photos.example.com/wanderbound"),
        }
    )
    app = FastAPI()
    install_frontend(app, settings)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://internal.example.com",
    ) as client:
        response = await client.get("/", headers={"Accept": "text/html"})

    parser = MetadataParser()
    parser.feed(response.text)

    assert response.status_code == 200
    assert parser.links["canonical"] == "https://photos.example.com/wanderbound/"
    assert parser.meta["og:url"] == "https://photos.example.com/wanderbound/"
    assert (
        parser.meta["og:image"] == "https://photos.example.com/wanderbound/og-image.png"
    )
    assert (
        parser.meta["twitter:image"]
        == "https://photos.example.com/wanderbound/og-image.png"
    )
