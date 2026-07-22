from typing import TYPE_CHECKING

from starlette.datastructures import URL
from starlette.middleware.gzip import GZipMiddleware

from app.core.config import Settings

if TYPE_CHECKING:
    from fastapi import FastAPI, Request, Response
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

    @app.middleware("http")
    async def response_headers(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = content_security_policy
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
