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
from app.api.v1.routes.uploads import UploadHTTPException
from app.core.config import get_settings
from app.core.http_clients import lifespan_clients
from app.core.locks import try_advisory_lock
from app.core.logging import setup_logging
from app.core.sentry import setup_sentry
from app.frontend import install_frontend
from app.logic.export import lifespan as export_lifespan
from app.logic.external_media.undo import lifespan as undo_lifespan
from app.logic.media_upgrade.pipeline import cleanup_orphaned_tmp
from app.logic.pdf import lifespan as pdf_lifespan
from app.logic.segment_routes import set_route_enrichment_http_clients
from app.logic.session import cancel_all_sessions
from app.logic.uploads.cleanup import upload_cleanup_loop
from app.logic.workflows.processing import set_processing_workflow_http_clients
from app.logic.workflows.recovery import (
    WorkflowAdminState,
    workflow_admin_election_loop,
    workflow_heartbeat_loop,
    workflow_recovery_loop,
)
from app.logic.workflows.runtime import destroy_dbos, launch_dbos
from app.services.upload_store import build_upload_store

if TYPE_CHECKING:
    from fastapi.routing import APIRoute

settings = get_settings()
setup_logging(use_console=settings.ENVIRONMENT == "local", log_level=settings.LOG_LEVEL)
setup_sentry(settings)

logger = structlog.get_logger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    return route.name


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:  # noqa: PLR0915
    settings.USERS_FOLDER.mkdir(parents=True, exist_ok=True)
    await cleanup_orphaned_tmp(settings.USERS_FOLDER)
    upload_store = build_upload_store(settings)

    # ffmpeg is still used for HDR tonemap + transcoding in media upgrade.
    # Probing moved to PyAV; ffprobe is no longer needed.
    path = shutil.which("ffmpeg")
    if path:
        logger.info("ffmpeg.available", path=path)
    else:
        logger.warning("ffmpeg.missing")

    async with (
        pdf_lifespan() as browser_manager,
        export_lifespan(),
        undo_lifespan(),
        lifespan_clients() as http,
    ):
        app.state.browser_manager = browser_manager
        app.state.http = http
        app.state.upload_store = upload_store
        set_processing_workflow_http_clients(http)
        set_route_enrichment_http_clients(http)
        try:
            async with try_advisory_lock("dbos-admin") as admin_lock_acquired:
                admin_state = WorkflowAdminState(
                    has_admin_server=(
                        settings.DBOS_RUN_ADMIN_SERVER and admin_lock_acquired
                    )
                )
                launch_dbos(settings, run_admin_server=admin_state.has_admin_server)

                async def promote_to_admin() -> None:
                    logger.info("workflow.admin_promoted")
                    destroy_dbos()
                    launch_dbos(settings, run_admin_server=True)

                heartbeat_task = asyncio.create_task(
                    workflow_heartbeat_loop(
                        settings,
                        has_admin_server=lambda: admin_state.has_admin_server,
                    )
                )
                upload_cleanup_task = asyncio.create_task(
                    upload_cleanup_loop(
                        upload_store, settings.DATA_FOLDER / "upload-work"
                    )
                )
                recovery_task = (
                    asyncio.create_task(workflow_recovery_loop(settings))
                    if admin_state.has_admin_server
                    else None
                )
                election_task = (
                    asyncio.create_task(
                        workflow_admin_election_loop(
                            settings,
                            admin_state,
                            promote_to_admin=promote_to_admin,
                        )
                    )
                    if settings.DBOS_RUN_ADMIN_SERVER
                    and not admin_state.has_admin_server
                    else None
                )
                try:
                    yield
                finally:
                    upload_cleanup_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await upload_cleanup_task
                    heartbeat_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await heartbeat_task
                    if recovery_task is not None:
                        recovery_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await recovery_task
                    if election_task is not None:
                        election_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await election_task
                    destroy_dbos()
        finally:
            upload_store.close()
            set_route_enrichment_http_clients(None)
            set_processing_workflow_http_clients(None)
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


@app.exception_handler(UploadHTTPException)
async def _upload_error(_request: Request, exc: UploadHTTPException) -> JSONResponse:
    return JSONResponse({"message": exc.detail}, status_code=exc.status_code)


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


install_frontend(app, settings)
