from __future__ import annotations

import html
from typing import TYPE_CHECKING

from starlette.datastructures import URL, Headers, MutableHeaders
from starlette.middleware.gzip import GZipMiddleware

from app.core.config import Settings

if TYPE_CHECKING:
    from fastapi import FastAPI, Request, Response
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp, Message, Receive, Scope, Send


_PUBLIC_URL_TOKEN = b"__WANDERBOUND_PUBLIC_URL__"


class _FrontendMetadataMiddleware:
    def __init__(self, app: ASGIApp, public_url: str) -> None:
        self.app = app
        self.public_url = html.escape(public_url.rstrip("/"), quote=True).encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET":
            await self.app(scope, receive, send)
            return

        await self.app(scope, receive, _MetadataResponseSender(send, self.public_url))


class _MetadataResponseSender:
    def __init__(self, send: Send, public_url: bytes) -> None:
        self.send = send
        self.public_url = public_url
        self.response_start: Message | None = None
        self.body = bytearray()
        self.is_html = False

    async def __call__(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = Headers(raw=message["headers"])
            self.is_html = headers.get("content-type", "").startswith("text/html")
            if self.is_html:
                self.response_start = message
                return

        elif message["type"] == "http.response.body" and self.is_html:
            self.body.extend(message.get("body", b""))
            if message.get("more_body", False):
                return

            await self._send_rendered()
            return

        await self.send(message)

    async def _send_rendered(self) -> None:
        if self.response_start is None:
            raise RuntimeError("HTML response body arrived before headers")

        rendered = bytes(self.body).replace(_PUBLIC_URL_TOKEN, self.public_url)
        headers = MutableHeaders(scope=self.response_start)
        headers["content-length"] = str(len(rendered))
        for header in ("etag", "last-modified"):
            if header in headers:
                del headers[header]
        await self.send(self.response_start)
        await self.send(
            {
                "type": "http.response.body",
                "body": rendered,
                "more_body": False,
            }
        )


def _content_security_policy(settings: Settings) -> str:
    upload_url = URL(str(settings.UPLOAD_S3_PUBLIC_ENDPOINT_URL))
    if settings.UPLOAD_S3_ADDRESSING_STYLE == "virtual":
        upload_url = upload_url.replace(
            hostname=f"{settings.UPLOAD_S3_BUCKET}.{upload_url.hostname}"
        )
    upload_url = upload_url.replace(
        path="", query="", fragment="", username=None, password=None
    )

    connect_sources = [
        "'self'",
        str(upload_url),
        "https://api.mapbox.com",
        "https://events.mapbox.com",
        "https://accounts.google.com/gsi/",
        "https://login.microsoftonline.com",
        "https://cloudflareinsights.com",
    ]
    if settings.PUBLIC_SENTRY_DSN:
        connect_sources.append(
            str(
                URL(str(settings.PUBLIC_SENTRY_DSN)).replace(
                    path="", query="", fragment="", username=None, password=None
                )
            )
        )

    return "; ".join(
        [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' "
            "https://accounts.google.com/gsi/client "
            "https://api.mapbox.com/mapbox-gl-js/plugins/ "
            "https://static.cloudflareinsights.com",
            "style-src 'self' 'unsafe-inline' https://accounts.google.com",
            "img-src 'self' data: blob: https://api.mapbox.com "
            "https://*.tiles.mapbox.com https://lh3.googleusercontent.com",
            "font-src 'self'",
            f"connect-src {' '.join(connect_sources)}",
            "frame-src https://accounts.google.com/gsi/",
            "worker-src 'self' blob:",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
    )


def install_frontend(app: FastAPI, settings: Settings) -> None:
    content_security_policy = _content_security_policy(settings)

    app.add_middleware(
        _FrontendMetadataMiddleware,
        public_url=str(settings.PUBLIC_URL),
    )

    @app.middleware("http")
    async def response_headers(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = content_security_policy
        if settings.APP_VERSION:
            response.headers["X-Wanderbound-Version"] = settings.APP_VERSION
        if request.url.path.startswith("/assets/") and response.status_code < 400:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif response.headers.get("Content-Type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.add_middleware(GZipMiddleware, minimum_size=256, compresslevel=6)
    app.frontend(
        "/",
        directory=settings.FRONTEND_DIRECTORY,
        check_dir=settings.ENVIRONMENT == "production",
    )
