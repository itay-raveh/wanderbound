import logging
import shutil
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import NoResultFound
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.http_clients import lifespan_clients
from app.core.logging import setup_logging
from app.core.sentry import setup_sentry
from app.logic.chunked_upload import upload_store
from app.logic.export import lifespan as export_lifespan
from app.logic.media_upgrade.pipeline import cleanup_orphaned_tmp
from app.logic.pdf import lifespan as pdf_lifespan
from app.logic.session import cancel_all_sessions

if TYPE_CHECKING:
    from fastapi.routing import APIRoute

settings = get_settings()
setup_logging(use_console=settings.ENVIRONMENT == "local", log_level=settings.LOG_LEVEL)
setup_sentry(settings)

logger = logging.getLogger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    return route.name


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings.USERS_FOLDER.mkdir(parents=True, exist_ok=True)
    await cleanup_orphaned_tmp(settings.USERS_FOLDER)

    # ffmpeg is still used for HDR tonemap + transcoding in media upgrade.
    # Probing moved to PyAV; ffprobe is no longer needed.
    path = shutil.which("ffmpeg")
    if path:
        logger.info("ffmpeg available at %s", path)
    else:
        logger.warning("ffmpeg not found on PATH - video features will fail")

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

app.add_middleware(CorrelationIdMiddleware)

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
