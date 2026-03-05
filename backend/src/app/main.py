import http
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api
from app.core.logging import config_logger
from app.models.db import init_db

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from fastapi.routing import APIRoute

logger = config_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    await init_db()
    yield


def _generate_unique_id(route: APIRoute) -> str:
    return route.name


app = FastAPI(
    title="Polarsteps Album Generator",
    lifespan=lifespan,
    generate_unique_id_function=_generate_unique_id,
)
app.include_router(api, prefix="/api/v1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_process_time_header(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = uuid4()

    logger.info(
        "{%s}[%s:%-5s] %-5s %s",
        request_id,
        request.client.host if request.client else "unknown",
        request.client.port if request.client else "unknown",
        request.method,
        request.url.path,
    )

    start_time = time.perf_counter()
    response = await call_next(request)
    end_time = time.perf_counter()

    logger.info(
        "{%s}[%s:%-5s] %-5s %s [%s] %s %s [/] (%d ms)",
        request_id,
        request.client.host if request.client else "unknown",
        request.client.port if request.client else "unknown",
        request.method,
        request.url.path,
        "on red" if response.status_code >= 400 else "on green",
        response.status_code,
        http.HTTPStatus(response.status_code).phrase,
        (end_time - start_time) * 1000,
    )

    return response
