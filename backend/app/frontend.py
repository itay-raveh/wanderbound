from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, Request, Response
from starlette.middleware.gzip import GZipMiddleware

from app.core.config import PublicSettings, Settings, get_settings

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint

router = APIRouter(tags=["config"])


def _url_origin(value: object) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(str(value))
    if not parsed.scheme or not parsed.hostname:
        return None
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def _content_security_policy(settings: Settings) -> str:
    connect_sources = [
        "'self'",
        str(settings.UPLOAD_S3_PUBLIC_ENDPOINT_URL).rstrip("/"),
        "https://api.mapbox.com",
        "https://events.mapbox.com",
        "https://accounts.google.com/gsi/",
        "https://login.microsoftonline.com",
        "https://cloudflareinsights.com",
    ]
    if sentry_origin := _url_origin(settings.PUBLIC_SENTRY_DSN):
        connect_sources.append(sentry_origin)

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


@router.get("/config")
def public_config(response: Response) -> PublicSettings:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    public_values = settings.model_dump(include=set(PublicSettings.model_fields))
    return PublicSettings.model_validate(public_values)


def install_frontend(application: FastAPI, settings: Settings) -> None:
    content_security_policy = _content_security_policy(settings)

    @application.middleware("http")
    async def response_headers(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = content_security_policy

        if request.url.path.startswith("/assets/") and response.status_code < 400:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif response.headers.get("Content-Type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    application.add_middleware(GZipMiddleware, minimum_size=256, compresslevel=6)
    application.include_router(router, prefix=settings.API_V1_STR)
    application.frontend(
        "/",
        directory=settings.FRONTEND_DIRECTORY,
        fallback="index.html",
        check_dir=False,
    )
