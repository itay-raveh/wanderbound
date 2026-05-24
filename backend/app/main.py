import asyncio
import shutil
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING

import structlog
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import NoResultFound
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.http_clients import lifespan_clients
from app.core.locks import try_advisory_lock
from app.core.logging import setup_logging
from app.core.sentry import setup_sentry
from app.logic.chunked_upload import upload_store
from app.logic.export import lifespan as export_lifespan
from app.logic.media_upgrade.pipeline import cleanup_orphaned_tmp
from app.logic.pdf import lifespan as pdf_lifespan
from app.logic.session import cancel_all_sessions
from app.logic.workflows.processing import set_processing_workflow_http_clients
from app.logic.workflows.recovery import workflow_heartbeat_loop, workflow_recovery_loop
from app.logic.workflows.runtime import destroy_dbos, launch_dbos

if TYPE_CHECKING:
    from fastapi.routing import APIRoute

settings = get_settings()
setup_logging(use_console=settings.ENVIRONMENT == "local", log_level=settings.LOG_LEVEL)
setup_sentry(settings)

logger = structlog.get_logger(__name__)


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
        logger.info("ffmpeg.available", path=path)
    else:
        logger.warning("ffmpeg.missing")

    async with try_advisory_lock("dbos-admin") as admin_lock_acquired:
        has_admin_server = settings.DBOS_RUN_ADMIN_SERVER and admin_lock_acquired
        launch_dbos(settings, run_admin_server=has_admin_server)
        heartbeat_task = asyncio.create_task(
            workflow_heartbeat_loop(settings, has_admin_server=has_admin_server)
        )
        recovery_task = (
            asyncio.create_task(workflow_recovery_loop(settings))
            if has_admin_server
            else None
        )
        try:
            async with (
                pdf_lifespan() as browser_manager,
                export_lifespan(),
                upload_store.lifespan(),
                lifespan_clients() as http,
            ):
                app.state.browser_manager = browser_manager
                app.state.http = http
                set_processing_workflow_http_clients(http)
                try:
                    yield
                finally:
                    set_processing_workflow_http_clients(None)
                    cancel_all_sessions()
        finally:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            if recovery_task is not None:
                recovery_task.cancel()
                with suppress(asyncio.CancelledError):
                    await recovery_task
            destroy_dbos()


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
    logger.debug("request.not_found", method=request.method, path=request.url.path)
    return JSONResponse({"detail": "Not found"}, status_code=404)


@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "request.unhandled_exception",
        method=request.method,
        path=request.url.path,
    )
    return JSONResponse({"detail": "Internal server error"}, status_code=500)
