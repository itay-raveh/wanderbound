from __future__ import annotations

from typing import TYPE_CHECKING

# FastAPI resolves this annotation when the route is registered.
from fastapi import Request  # noqa: TC002
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL
from starlette.middleware.gzip import GZipMiddleware

from app.core.config import Settings

if TYPE_CHECKING:
    from fastapi import FastAPI, Response
    from starlette.middleware.base import RequestResponseEndpoint


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
    templates = Jinja2Templates(directory=settings.FRONTEND_DIRECTORY)
    public_url = str(settings.PUBLIC_URL).rstrip("/")

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

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def frontend_index(request: Request) -> Response:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"public_url": public_url},
        )

    app.frontend(
        "/",
        directory=settings.FRONTEND_DIRECTORY,
        check_dir=settings.ENVIRONMENT == "production",
    )
