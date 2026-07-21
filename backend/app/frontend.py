from collections.abc import AsyncIterator
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from fastapi import APIRouter, FastAPI, Request, Response
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware

from app.core.config import PublicSettings, Settings, get_settings

if TYPE_CHECKING:
    from pydantic import AnyHttpUrl
    from starlette.middleware.base import RequestResponseEndpoint

router = APIRouter(tags=["config"])
_PUBLIC_URL_MARKER = "__WANDERBOUND_PUBLIC_URL__"


class _StreamingBodyResponse(Protocol):
    body_iterator: AsyncIterator[bytes | dict[str, str]]


def _origin(value: AnyHttpUrl, *, host: str | None = None) -> str:
    hostname = host or value.host
    if hostname is None:
        raise ValueError("URL must contain a hostname")
    default_port = 80 if value.scheme == "http" else 443
    port = f":{value.port}" if value.port != default_port else ""
    return f"{value.scheme}://{hostname}{port}"


def _upload_origin(settings: Settings) -> str:
    url = settings.UPLOAD_S3_PUBLIC_ENDPOINT_URL
    hostname = url.host
    if hostname is None:
        raise ValueError("UPLOAD_S3_PUBLIC_ENDPOINT_URL must contain a hostname")
    if settings.UPLOAD_S3_ADDRESSING_STYLE == "virtual":
        hostname = f"{settings.UPLOAD_S3_BUCKET}.{hostname}"
    return _origin(url, host=hostname)


def _content_security_policy(settings: Settings) -> str:
    connect_sources = [
        "'self'",
        _upload_origin(settings),
        "https://api.mapbox.com",
        "https://events.mapbox.com",
        "https://accounts.google.com/gsi/",
        "https://login.microsoftonline.com",
        "https://cloudflareinsights.com",
    ]
    if settings.PUBLIC_SENTRY_DSN:
        connect_sources.append(_origin(settings.PUBLIC_SENTRY_DSN))

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


async def _read_response_body(response: Response) -> bytes | None:
    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is None:
        return None
    chunks: list[bytes] = []
    async for chunk in body_iterator:
        if isinstance(chunk, dict):
            chunks.append(await run_in_threadpool(Path(chunk["path"]).read_bytes))
        else:
            chunks.append(bytes(chunk))
    return b"".join(chunks)


def _delete_headers(response: Response, *headers: str) -> None:
    for header in headers:
        if header in response.headers:
            del response.headers[header]


async def _render_social_metadata(
    response: Response, public_url: str, *, method: str
) -> Response:
    is_html = response.headers.get("Content-Type", "").startswith("text/html")
    if not is_html:
        return response
    if method == "HEAD":
        _delete_headers(response, "Content-Length", "ETag", "Last-Modified")
        return response
    if response.status_code != 200:
        return response

    body = await _read_response_body(response)
    if body is None:
        return response
    marker = _PUBLIC_URL_MARKER.encode()
    rendered = body.replace(marker, escape(public_url, quote=True).encode())
    streaming_response = cast("_StreamingBodyResponse", response)
    streaming_response.body_iterator = iterate_in_threadpool(iter([rendered]))
    response.headers["Content-Length"] = str(len(rendered))
    if rendered != body:
        _delete_headers(response, "ETag", "Last-Modified")
    return response


@router.get("/config")
def public_config(response: Response) -> PublicSettings:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    public_values = settings.model_dump(include=set(PublicSettings.model_fields))
    return PublicSettings.model_validate(public_values)


def install_frontend(app: FastAPI, settings: Settings) -> None:
    content_security_policy = _content_security_policy(settings)

    @app.middleware("http")
    async def response_headers(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response = await _render_social_metadata(
            response,
            str(settings.PUBLIC_URL).rstrip("/"),
            method=request.method,
        )
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

    app.add_middleware(GZipMiddleware, minimum_size=256, compresslevel=6)
    app.include_router(router, prefix=settings.API_V1_STR)
    app.frontend(
        "/",
        directory=settings.FRONTEND_DIRECTORY,
        check_dir=False,
    )
