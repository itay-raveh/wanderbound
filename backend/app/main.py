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
from app.core.logging import setup_logging
from app.core.sentry import setup_sentry
from app.frontend import install_frontend
from app.logic.export import lifespan as export_lifespan
from app.logic.external_media.undo import lifespan as undo_lifespan
from app.logic.media_upgrade.pipeline import cleanup_orphaned_tmp
from app.logic.pdf import lifespan as pdf_lifespan
from app.logic.segment_routes import (
    reconcile_missing_route_enrichments,
    set_route_enrichment_http_clients,
)
from app.logic.session import cancel_all_sessions
from app.logic.storage_metrics import storage_metrics_loop
from app.logic.uploads.cleanup import upload_cleanup_loop
from app.logic.workflows.media_hashes import (
    media_hash_reconciliation_loop,
    reconcile_missing_media_hash_backfills,
)
from app.logic.workflows.processing import set_processing_workflow_http_clients
from app.logic.workflows.runtime import destroy_dbos, launch_dbos
from app.services.upload_store import UploadStoreService, build_upload_store

if TYPE_CHECKING:
    from fastapi.routing import APIRoute

settings = get_settings()
setup_logging(use_console=settings.ENVIRONMENT == "local", log_level=settings.LOG_LEVEL)
setup_sentry(settings)

logger = structlog.get_logger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    return route.name


async def _reconcile_media_hashes() -> None:
    try:
        await reconcile_missing_media_hash_backfills()
    except Exception as exc:
        logger.exception(
            "media_hash.backfill_startup_reconciliation_failed",
            error_type=type(exc).__name__,
        )


async def _reconcile_segment_routes() -> None:
    try:
        await reconcile_missing_route_enrichments()
    except Exception as exc:
        logger.exception(
            "route_enrichment.startup_reconciliation_failed",
            error_type=type(exc).__name__,
        )


def _launch_background_tasks(
    upload_store: UploadStoreService,
) -> list[asyncio.Task[None]]:
    return [
        asyncio.create_task(storage_metrics_loop(settings.DATA_FOLDER)),
        asyncio.create_task(media_hash_reconciliation_loop()),
        asyncio.create_task(
            upload_cleanup_loop(upload_store, settings.DATA_FOLDER / "upload-work")
        ),
    ]


async def _cleanup_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task


@asynccontextmanager
async def _dbos_lifespan(
    upload_store: UploadStoreService,
) -> AsyncGenerator[None]:
    await launch_dbos(settings)
    await _reconcile_segment_routes()
    await _reconcile_media_hashes()
    tasks = _launch_background_tasks(upload_store)
    try:
        yield
    finally:
        await _cleanup_tasks(tasks)
        destroy_dbos()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
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
            async with _dbos_lifespan(upload_store):
                yield
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
