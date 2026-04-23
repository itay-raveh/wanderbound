import logging
import shutil
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber
from sqlalchemy.exc import NoResultFound
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.http_clients import lifespan_clients
from app.core.logging import SENTRY_IGNORED, setup_logging
from app.logic.chunked_upload import upload_store
from app.logic.export import lifespan as export_lifespan
from app.logic.media_upgrade.pipeline import cleanup_orphaned_tmp
from app.logic.pdf import lifespan as pdf_lifespan
from app.logic.session import cancel_all_sessions

if TYPE_CHECKING:
    from fastapi.routing import APIRoute

settings = get_settings()
setup_logging(use_rich=settings.ENVIRONMENT == "local", log_level=settings.LOG_LEVEL)

if settings.SENTRY_DSN:

    def _before_breadcrumb(crumb: dict, _hint: dict) -> dict | None:
        if crumb.get("category") in SENTRY_IGNORED:
            return None
        return crumb

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=settings.SENTRY_RELEASE,
        traces_sample_rate=0,
        enable_logs=True,
        integrations=[LoggingIntegration(event_level=logging.ERROR)],
        before_breadcrumb=_before_breadcrumb,
        # send_default_pii=False is required for a custom EventScrubber/denylist.
        send_default_pii=False,
        event_scrubber=EventScrubber(
            denylist=[
                *DEFAULT_DENYLIST,
                "access_token",
                "refresh_token",
                "code_verifier",
                "verifier",
                "credential",
            ],
            recursive=True,
        ),
    )

logger = logging.getLogger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    return route.name


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings.USERS_FOLDER.mkdir(parents=True, exist_ok=True)
    await cleanup_orphaned_tmp(settings.USERS_FOLDER)

    for binary in ("ffmpeg", "ffprobe"):
        path = shutil.which(binary)
        if path:
            logger.info("%s available at %s", binary, path)
        else:
            logger.warning("%s not found on PATH - video features will fail", binary)

    async with (
        pdf_lifespan() as browser_manager,
        export_lifespan(),
        upload_store.lifespan(),
        lifespan_clients() as http,
    ):
        app.state.browser_manager = browser_manager
        app.state.http = http
        try:
            yield
        finally:
            cancel_all_sessions()


app = FastAPI(
    title="Wanderbound",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,  # type: ignore[invalid-argument-type]
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="session",
    max_age=30 * 86400,  # 30 days
    same_site="lax",
    https_only=settings.ENVIRONMENT != "local",
)

app.include_router(v1_router, prefix=settings.API_V1_STR)


@app.exception_handler(NoResultFound)
async def _not_found(request: Request, _exc: NoResultFound) -> JSONResponse:
    logger.debug("Not found: %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Not found"}, status_code=404)


@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)
